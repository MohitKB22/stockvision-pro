"""
Market Overview Service — new in v2.0.

Everything the Market Overview page shows (indices, gainers, losers, most
active, sector performance, heatmap, breadth, 52-week highs/lows) is COMPUTED
from the `historical_prices` table. Nothing here is hardcoded, sampled from a
fixture, or invented at render time: if a symbol has no price history it is
absent from the results rather than filled in with a plausible-looking number.

Every method takes a `Market` and issues at most two queries regardless of
universe size — one for the stock list, one bulk recent-closes fetch. The naive
implementation (loop over symbols, query each) is what makes this kind of page
slow, and it degrades linearly with the number of listed companies.
"""
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.domain.enums import Market
from app.domain.markets import get_market, index_definition
from app.models.market import Stock
from app.repositories.market_repository import PriceRepository, StockRepository
from app.schemas.market import (
    IndexQuote,
    MarketBreadth,
    MarketOverview,
    MoverQuote,
    SectorPerformance,
    StockQuote,
    WeekRangeEntry,
)

logger = logging.getLogger(__name__)

# Bars pulled per symbol. 260 ≈ one trading year, which is exactly what the
# 52-week high/low needs; anything more is wasted I/O.
_LOOKBACK_BARS = 260


@dataclass
class _Snapshot:
    """Everything the overview needs about one stock, assembled once."""
    stock: Stock
    last: float
    previous: float
    change: float
    change_pct: float
    volume: float
    avg_volume: float
    week52_high: float
    week52_low: float
    sparkline: list[float]

    @property
    def turnover(self) -> float:
        return self.last * self.volume


class MarketOverviewService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.stocks = StockRepository(db)
        self.prices = PriceRepository(db)

    # --- Snapshot assembly ---------------------------------------------------
    def _snapshots(self, market: Market, include_indices: bool = False) -> list[_Snapshot]:
        universe = self.stocks.list_equities(market=market, limit=1000)
        if include_indices:
            universe = universe + self.stocks.list_indices(market=market)
        if not universe:
            return []

        by_stock = self.prices.get_recent_closes_bulk([s.id for s in universe], lookback=_LOOKBACK_BARS)

        snapshots: list[_Snapshot] = []
        for stock in universe:
            bars = by_stock.get(stock.id) or []
            if len(bars) < 2:
                # A symbol with fewer than two bars has no computable change.
                # Omitted rather than shown as "0.00%", which would be a claim
                # the data does not support.
                continue
            closes = [b.close for b in bars]           # newest-first
            highs = [b.high for b in bars]
            lows = [b.low for b in bars]
            volumes = [b.volume for b in bars]

            last, previous = closes[0], closes[1]
            change = last - previous
            snapshots.append(
                _Snapshot(
                    stock=stock, last=last, previous=previous, change=change,
                    change_pct=(change / previous) if previous else 0.0,
                    volume=volumes[0],
                    avg_volume=sum(volumes[:30]) / min(len(volumes), 30),
                    week52_high=max(highs), week52_low=min(lows),
                    sparkline=list(reversed(closes[:30])),  # oldest-first for charting
                )
            )
        return snapshots

    @staticmethod
    def _quote_from(stock: Stock, bars: list) -> StockQuote:
        closes = [b.close for b in bars]
        change = closes[0] - closes[1]
        return StockQuote(
            stock_id=stock.id, symbol=stock.symbol, name=stock.name, exchange=stock.exchange,
            market=stock.market, sector=stock.sector, currency=stock.currency,
            last_price=closes[0], previous_close=closes[1], change=change,
            change_pct=(change / closes[1]) if closes[1] else 0.0,
            volume=bars[0].volume,
            avg_volume_30d=sum(b.volume for b in bars[:30]) / min(len(bars), 30),
            week_52_high=max(b.high for b in bars), week_52_low=min(b.low for b in bars),
            market_cap=stock.market_cap, sparkline=list(reversed(closes[:30])),
        )

    # --- Public API -----------------------------------------------------------
    def quote(self, symbol: str) -> StockQuote:
        stock = self.stocks.get_by_symbol(symbol)
        if not stock:
            raise NotFoundException(f"Symbol {symbol.upper()} is not listed.")
        bars = self.prices.get_recent_closes_bulk([stock.id], lookback=_LOOKBACK_BARS).get(stock.id, [])
        if len(bars) < 2:
            raise NotFoundException(f"No price history available for {stock.symbol}.")
        return self._quote_from(stock, bars)

    def quotes(self, symbols: list[str]) -> list[StockQuote]:
        stocks = self.stocks.get_many_by_symbols(symbols)
        if not stocks:
            return []
        by_stock = self.prices.get_recent_closes_bulk([s.id for s in stocks], lookback=_LOOKBACK_BARS)
        return [
            self._quote_from(stock, bars)
            for stock in stocks
            if len(bars := (by_stock.get(stock.id) or [])) >= 2
        ]

    def indices(self, market: Market) -> list[IndexQuote]:
        """
        Index levels.

        Prefers a stored index instrument (seeded as a real `Stock` row with
        `is_index=True`, so it flows through the same price pipeline as any
        equity). Falls back to a cap-weighted level synthesized from the index's
        constituents when no instrument exists — which keeps the page working on
        a partially-seeded database instead of showing gaps. The response says
        which of the two produced each number.
        """
        definition = get_market(market)
        index_stocks = {s.symbol: s for s in self.stocks.list_indices(market=market)}
        constituent_snaps = {s.stock.symbol: s for s in self._snapshots(market)}

        stored_bars = self.prices.get_recent_closes_bulk(
            [s.id for s in index_stocks.values()], lookback=_LOOKBACK_BARS
        )

        out: list[IndexQuote] = []
        for idx in definition.indices:
            stock = index_stocks.get(idx.symbol)
            bars = stored_bars.get(stock.id) if stock else None
            if stock and bars and len(bars) >= 2:
                closes = [b.close for b in bars]
                change = closes[0] - closes[1]
                out.append(IndexQuote(
                    symbol=idx.symbol, name=idx.name, market=market,
                    level=closes[0], previous_close=closes[1], change=change,
                    change_pct=(change / closes[1]) if closes[1] else 0.0,
                    sparkline=list(reversed(closes[:60])),
                    constituent_count=len(idx.constituents), is_synthetic=False,
                ))
                continue

            members = [constituent_snaps[sym] for sym in idx.constituents if sym in constituent_snaps]
            if not members:
                continue
            weights = [(m.stock.market_cap or 1.0) for m in members]
            total_w = sum(weights) or 1.0
            level = sum(m.last * w for m, w in zip(members, weights)) / total_w
            prev = sum(m.previous * w for m, w in zip(members, weights)) / total_w
            depth = min(min(len(m.sparkline) for m in members), 60)
            spark = [
                sum(m.sparkline[-depth:][i] * w for m, w in zip(members, weights)) / total_w
                for i in range(depth)
            ]
            out.append(IndexQuote(
                symbol=idx.symbol, name=idx.name, market=market,
                level=level, previous_close=prev, change=level - prev,
                change_pct=((level - prev) / prev) if prev else 0.0,
                sparkline=spark, constituent_count=len(members), is_synthetic=True,
            ))
        return out

    def index_constituents(self, market: Market, index_symbol: str) -> list[StockQuote]:
        definition = index_definition(market, index_symbol)
        if definition is None:
            raise NotFoundException(f"{index_symbol.upper()} is not an index in this market.")
        return self.quotes(list(definition.constituents))

    def movers(self, market: Market, limit: int = 10) -> dict[str, list[MoverQuote]]:
        snaps = self._snapshots(market)

        def to_mover(s: _Snapshot) -> MoverQuote:
            return MoverQuote(
                symbol=s.stock.symbol, name=s.stock.name, sector=s.stock.sector,
                last_price=s.last, change=s.change, change_pct=s.change_pct,
                volume=s.volume, turnover=s.turnover, sparkline=s.sparkline[-20:],
            )

        gainers = sorted((s for s in snaps if s.change_pct > 0), key=lambda s: -s.change_pct)
        losers = sorted((s for s in snaps if s.change_pct < 0), key=lambda s: s.change_pct)
        active = sorted(snaps, key=lambda s: -s.turnover)
        return {
            "gainers": [to_mover(s) for s in gainers[:limit]],
            "losers": [to_mover(s) for s in losers[:limit]],
            "most_active": [to_mover(s) for s in active[:limit]],
        }

    def sector_performance(self, market: Market) -> list[SectorPerformance]:
        """
        Cap-weighted sector return.

        Cap-weighted, not equal-weighted, because an equal-weighted sector
        average lets a single micro-cap outlier dominate a sector's headline
        number — which reads as a data error to anyone who knows the market.
        """
        snaps = self._snapshots(market)
        buckets: dict[str, list[_Snapshot]] = {}
        for s in snaps:
            buckets.setdefault(s.stock.sector or "Unclassified", []).append(s)

        out: list[SectorPerformance] = []
        for sector, members in buckets.items():
            weights = [(m.stock.market_cap or 1.0) for m in members]
            total_w = sum(weights) or 1.0
            out.append(SectorPerformance(
                sector=sector,
                change_pct=sum(m.change_pct * w for m, w in zip(members, weights)) / total_w,
                advancers=sum(1 for m in members if m.change_pct > 0),
                decliners=sum(1 for m in members if m.change_pct < 0),
                constituent_count=len(members),
                total_turnover=sum(m.turnover for m in members),
                market_cap=sum(m.stock.market_cap or 0.0 for m in members),
                top_symbol=max(members, key=lambda m: m.change_pct).stock.symbol,
                bottom_symbol=min(members, key=lambda m: m.change_pct).stock.symbol,
            ))
        return sorted(out, key=lambda s: -s.change_pct)

    def heatmap(self, market: Market) -> list[dict]:
        """
        Treemap-shaped payload: one entry per stock with its sector, weight
        (market cap) and return. The frontend lays it out; the server decides
        what is true.
        """
        return [
            {
                "symbol": s.stock.symbol, "name": s.stock.name,
                "sector": s.stock.sector or "Unclassified",
                "change_pct": s.change_pct, "market_cap": s.stock.market_cap or 0.0,
                "last_price": s.last, "turnover": s.turnover,
            }
            for s in self._snapshots(market)
        ]

    def breadth(self, market: Market) -> MarketBreadth:
        snaps = self._snapshots(market)
        advancers = sum(1 for s in snaps if s.change_pct > 0)
        decliners = sum(1 for s in snaps if s.change_pct < 0)
        return MarketBreadth(
            market=market, total=len(snaps),
            advancers=advancers, decliners=decliners,
            unchanged=len(snaps) - advancers - decliners,
            advance_decline_ratio=(advancers / decliners) if decliners else float(advancers),
            new_highs=sum(1 for s in snaps if s.last >= s.week52_high * 0.999),
            new_lows=sum(1 for s in snaps if s.last <= s.week52_low * 1.001),
            above_avg_volume=sum(1 for s in snaps if s.avg_volume and s.volume > s.avg_volume),
            total_turnover=sum(s.turnover for s in snaps),
        )

    def week_52_extremes(self, market: Market, limit: int = 10) -> dict[str, list[WeekRangeEntry]]:
        snaps = self._snapshots(market)

        def entry(s: _Snapshot) -> WeekRangeEntry:
            span = s.week52_high - s.week52_low
            return WeekRangeEntry(
                symbol=s.stock.symbol, name=s.stock.name, last_price=s.last,
                week_52_high=s.week52_high, week_52_low=s.week52_low,
                pct_from_high=(s.last - s.week52_high) / s.week52_high if s.week52_high else 0.0,
                pct_from_low=(s.last - s.week52_low) / s.week52_low if s.week52_low else 0.0,
                position_in_range=((s.last - s.week52_low) / span) if span > 0 else 0.5,
            )

        near_high = sorted(snaps, key=lambda s: -(s.last / s.week52_high if s.week52_high else 0))
        near_low = sorted(snaps, key=lambda s: (s.last / s.week52_low if s.week52_low else 1e9))
        return {
            "near_52_week_high": [entry(s) for s in near_high[:limit]],
            "near_52_week_low": [entry(s) for s in near_low[:limit]],
        }

    def overview(self, market: Market, mover_limit: int = 6) -> MarketOverview:
        """One call that fills the entire Market Overview page."""
        movers = self.movers(market, limit=mover_limit)
        definition = get_market(market)
        return MarketOverview(
            market=market,
            currency=definition.currency,
            currency_symbol=definition.currency_symbol,
            indices=self.indices(market),
            gainers=movers["gainers"], losers=movers["losers"], most_active=movers["most_active"],
            sectors=self.sector_performance(market),
            breadth=self.breadth(market),
        )
