"""
Portfolio position-replay tests.

CHANGE LOG (v2.0): `replay_orders` now returns `Position` objects rather than
(quantity, average_cost) tuples, because it also tracks REALIZED P&L — which v1
silently discarded, understating total return for any portfolio that had taken
profit. These tests are updated to the new shape and extended to cover realized
P&L and transaction-cost capitalisation.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.domain.enums import OrderSide, OrderStatus
from app.models.portfolio import Order
from app.services.portfolio_service import replay_orders

STOCK_A = uuid.uuid4()
STOCK_B = uuid.uuid4()


_SEQUENCE = iter(range(1, 10_000))


def make_order(stock_id, side, quantity, price, transaction_cost=0.0, slippage=0.0) -> Order:
    """
    Each order gets a strictly increasing `executed_at`.

    replay_orders sorts by execution time, and `datetime.now()` called in a tight
    loop can return the SAME timestamp twice — which made ordering
    non-deterministic and the buy/sell/buy test intermittently flaky.
    """
    return Order(
        stock_id=stock_id,
        side=side,
        quantity=quantity,
        price=price,
        transaction_cost=transaction_cost,
        slippage=slippage,
        status=OrderStatus.FILLED,
        executed_at=datetime.now(timezone.utc) + timedelta(seconds=next(_SEQUENCE)),
    )


class TestReplayOrders:
    def test_single_buy(self):
        orders = [make_order(STOCK_A, OrderSide.BUY, 10, 100.0)]
        positions = replay_orders(orders)
        position = positions[STOCK_A]
        qty, avg_cost = position.quantity, position.average_cost
        assert qty == 10
        assert avg_cost == pytest.approx(100.0)

    def test_two_buys_computes_weighted_average_cost(self):
        # Buy 10 @ 100, then 10 @ 200 -> weighted avg cost = (10*100+10*200)/20 = 150
        orders = [
            make_order(STOCK_A, OrderSide.BUY, 10, 100.0),
            make_order(STOCK_A, OrderSide.BUY, 10, 200.0),
        ]
        position = replay_orders(orders)[STOCK_A]
        qty, avg_cost = position.quantity, position.average_cost
        assert qty == 20
        assert avg_cost == pytest.approx(150.0)

    def test_sell_reduces_quantity_but_not_average_cost(self):
        orders = [
            make_order(STOCK_A, OrderSide.BUY, 10, 100.0),
            make_order(STOCK_A, OrderSide.SELL, 4, 500.0),  # sell price shouldn't affect remaining avg cost
        ]
        position = replay_orders(orders)[STOCK_A]
        qty, avg_cost = position.quantity, position.average_cost
        assert qty == 6
        assert avg_cost == pytest.approx(100.0)

    def test_selling_entire_position_leaves_zero_quantity(self):
        """
        BEHAVIOUR CHANGE (v2.0): a fully-closed position is no longer dropped from
        the result. It is retained with quantity 0 so its realized P&L remains
        reportable — dropping it is how a portfolio's realized return silently
        disappears. `_rebuild_holdings` still filters zero-quantity rows before
        writing the holdings projection, so nothing downstream sees a phantom
        holding.
        """
        orders = [
            make_order(STOCK_A, OrderSide.BUY, 10, 100.0),
            make_order(STOCK_A, OrderSide.SELL, 10, 120.0),
        ]
        positions = replay_orders(orders)
        assert positions[STOCK_A].quantity == 0.0
        assert positions[STOCK_A].realized_pnl == pytest.approx(200.0)

    def test_overselling_is_clamped_to_zero_not_negative(self):
        """Selling more than currently held (e.g. due to a data entry error)
        must not produce a negative quantity position."""
        orders = [
            make_order(STOCK_A, OrderSide.BUY, 5, 100.0),
            make_order(STOCK_A, OrderSide.SELL, 8, 100.0),
        ]
        positions = replay_orders(orders)
        # Quantity clamps to 0 and, with no realized P&L to report, the entry is
        # dropped as pure noise — see replay_orders' final filter.
        assert STOCK_A not in positions

    def test_buy_sell_buy_recomputes_average_cost_correctly(self):
        """A classic edge case: cost basis after a partial sell followed by
        a new buy at a different price must reflect only the REMAINING
        shares' original cost, blended with the new purchase."""
        orders = [
            make_order(STOCK_A, OrderSide.BUY, 10, 100.0),   # 10 @ 100
            make_order(STOCK_A, OrderSide.SELL, 5, 999.0),    # -> 5 @ 100 remain
            make_order(STOCK_A, OrderSide.BUY, 5, 300.0),     # + 5 @ 300 -> 10 @ avg 200
        ]
        position = replay_orders(orders)[STOCK_A]
        qty, avg_cost = position.quantity, position.average_cost
        assert qty == 10
        assert avg_cost == pytest.approx(200.0)

    def test_multiple_stocks_tracked_independently(self):
        orders = [
            make_order(STOCK_A, OrderSide.BUY, 10, 100.0),
            make_order(STOCK_B, OrderSide.BUY, 5, 50.0),
        ]
        positions = replay_orders(orders)
        assert positions[STOCK_A].quantity == 10
        assert positions[STOCK_A].average_cost == pytest.approx(100.0)
        assert positions[STOCK_B].quantity == 5
        assert positions[STOCK_B].average_cost == pytest.approx(50.0)

    def test_empty_orders_gives_empty_positions(self):
        assert replay_orders([]) == {}


class TestRealizedPnL:
    """New in v2.0 — v1 threw this information away entirely."""

    def test_sell_books_realized_pnl(self):
        positions = replay_orders([
            make_order(STOCK_A, OrderSide.BUY, 10, 100.0),
            make_order(STOCK_A, OrderSide.SELL, 4, 150.0),
        ])
        assert positions[STOCK_A].realized_pnl == pytest.approx(200.0)  # 4 x (150 - 100)
        assert positions[STOCK_A].quantity == pytest.approx(6.0)

    def test_sell_at_a_loss_books_negative_realized_pnl(self):
        positions = replay_orders([
            make_order(STOCK_A, OrderSide.BUY, 10, 100.0),
            make_order(STOCK_A, OrderSide.SELL, 5, 80.0),
        ])
        assert positions[STOCK_A].realized_pnl == pytest.approx(-100.0)

    def test_transaction_costs_are_capitalised_into_average_cost(self):
        """Brokerage and slippage are genuinely part of what a position cost;
        excluding them overstates every P&L figure downstream."""
        positions = replay_orders([
            make_order(STOCK_A, OrderSide.BUY, 10, 100.0, transaction_cost=50.0, slippage=10.0),
        ])
        # (10 x 100 + 60) / 10 = 106
        assert positions[STOCK_A].average_cost == pytest.approx(106.0)

    def test_frictions_reduce_realized_pnl_on_a_sell(self):
        positions = replay_orders([
            make_order(STOCK_A, OrderSide.BUY, 10, 100.0),
            make_order(STOCK_A, OrderSide.SELL, 5, 120.0, transaction_cost=20.0),
        ])
        assert positions[STOCK_A].realized_pnl == pytest.approx(80.0)  # 5 x 20 - 20

    def test_orders_are_replayed_in_execution_order_not_list_order(self):
        """Order history arrives sorted from the repository, but replay must not
        DEPEND on that — an out-of-order list would otherwise silently produce a
        different average cost."""
        first = make_order(STOCK_A, OrderSide.BUY, 10, 100.0)
        second = make_order(STOCK_A, OrderSide.BUY, 10, 200.0)
        assert (
            replay_orders([second, first])[STOCK_A].average_cost
            == pytest.approx(replay_orders([first, second])[STOCK_A].average_cost)
        )
