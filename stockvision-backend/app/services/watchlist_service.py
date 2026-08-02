"""
Watchlist Service — new in v2.0.

The reference design shows a persistent watchlist strip on the dashboard and a
dedicated watchlist page. Neither had any backend before; the symbols in the old
UI were literals in a component file.
"""
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import AlreadyExistsException, NotFoundException
from app.domain.enums import Market
from app.domain.markets import get_market
from app.models.system import Watchlist, WatchlistItem
from app.repositories.market_repository import StockRepository
from app.repositories.system_repository import WatchlistItemRepository, WatchlistRepository
from app.schemas.watchlist import WatchlistItemPublic, WatchlistPublic
from app.services.market_overview_service import MarketOverviewService


class WatchlistService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = WatchlistRepository(db)
        self.items = WatchlistItemRepository(db)
        self.stocks = StockRepository(db)
        self.overview = MarketOverviewService(db)

    def ensure_default(self, market: Market) -> Watchlist:
        """
        Guarantees a watchlist exists for the market.

        Without this a fresh database made the watchlist page render an empty
        state the user could not escape — there was no way to create the first
        list from the UI. Now the first read creates it.
        """
        existing = self.repo.get_default(market)
        if existing:
            return existing
        return self.repo.create(
            Watchlist(name=f"{get_market(market).name} Watchlist", market=market, is_default=True)
        )

    def list_all(self, market: Market) -> list[WatchlistPublic]:
        self.ensure_default(market)
        return [self._to_public(w) for w in self.repo.list_all(market)]

    def get(self, watchlist_id: uuid.UUID) -> WatchlistPublic:
        watchlist = self.repo.get_with_items(watchlist_id)
        if not watchlist:
            raise NotFoundException("Watchlist not found")
        return self._to_public(watchlist)

    def get_default(self, market: Market) -> WatchlistPublic:
        return self._to_public(self.ensure_default(market))

    def create(self, name: str, market: Market) -> WatchlistPublic:
        return self._to_public(self.repo.create(Watchlist(name=name, market=market)))

    def delete(self, watchlist_id: uuid.UUID) -> None:
        watchlist = self.repo.get(watchlist_id)
        if not watchlist:
            raise NotFoundException("Watchlist not found")
        self.repo.delete(watchlist)

    def add_symbol(
        self, watchlist_id: uuid.UUID, symbol: str,
        alert_above: float | None = None, alert_below: float | None = None,
    ) -> WatchlistPublic:
        watchlist = self.repo.get(watchlist_id)
        if not watchlist:
            raise NotFoundException("Watchlist not found")

        stock = self.stocks.get_by_symbol(symbol)
        if not stock:
            raise NotFoundException(f"Symbol {symbol.upper()} is not listed.")
        if self.items.find(watchlist_id, stock.id):
            raise AlreadyExistsException(f"{stock.symbol} is already on this watchlist.")

        self.items.create(
            WatchlistItem(
                watchlist_id=watchlist_id, stock_id=stock.id,
                position=self.items.next_position(watchlist_id),
                alert_above=alert_above, alert_below=alert_below,
            )
        )
        return self.get(watchlist_id)

    def remove_symbol(self, watchlist_id: uuid.UUID, symbol: str) -> WatchlistPublic:
        stock = self.stocks.get_by_symbol(symbol)
        if not stock:
            raise NotFoundException(f"Symbol {symbol.upper()} is not listed.")
        item = self.items.find(watchlist_id, stock.id)
        if not item:
            raise NotFoundException(f"{stock.symbol} is not on this watchlist.")
        self.items.delete(item)
        return self.get(watchlist_id)

    def _to_public(self, watchlist: Watchlist) -> WatchlistPublic:
        symbols = [item.stock.symbol for item in watchlist.items]
        quotes = {q.symbol: q for q in self.overview.quotes(symbols)} if symbols else {}

        items: list[WatchlistItemPublic] = []
        for item in watchlist.items:
            quote = quotes.get(item.stock.symbol)
            items.append(
                WatchlistItemPublic(
                    id=item.id, symbol=item.stock.symbol, name=item.stock.name,
                    sector=item.stock.sector, position=item.position,
                    alert_above=item.alert_above, alert_below=item.alert_below,
                    quote=quote,
                    # An alert is "triggered" only when we actually have a price
                    # to compare against — never inferred from a missing quote,
                    # which would fire spurious alerts on stale data.
                    alert_triggered=bool(
                        quote and (
                            (item.alert_above is not None and quote.last_price >= item.alert_above)
                            or (item.alert_below is not None and quote.last_price <= item.alert_below)
                        )
                    ),
                )
            )

        return WatchlistPublic(
            id=watchlist.id, name=watchlist.name, market=watchlist.market,
            is_default=watchlist.is_default, item_count=len(items), items=items,
        )
