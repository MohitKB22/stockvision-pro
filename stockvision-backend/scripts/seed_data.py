"""
Seeds a fresh database with a browsable, realistic system in one command:

    python3 scripts/seed_data.py            # both markets
    python3 scripts/seed_data.py --market IN
    python3 scripts/seed_data.py --reset    # drop and recreate first

What it creates, per market:
  * The index instruments and the equity universe defined in app/domain/markets.py
  * ~3 years of synthetic daily OHLCV per symbol (see the honesty note below)
  * A default portfolio with a realistic order ledger, including one partial exit
  * A default watchlist
  * A news corpus, scored by the same sentiment engine the API uses

CHANGE LOG (v2.0): the demo-user block is gone — there are no accounts. Seeding
now covers both markets and populates news, watchlists and portfolios (previously
absent, which is why the old UI had to hardcode its data), and gives each symbol a
plausible base price and market cap rather than starting everything at $150.

HONESTY NOTE: price history is SYNTHETIC (geometric Brownian motion with
regime-switching volatility — see scripts/generate_synthetic_data.py). This
environment has no network access to a market-data provider. The real provider
clients exist and are wired to the Celery refresh task
(app/services/market_data_providers.py, app/worker.py); supply an API key and the
same tables fill with real bars. Nothing downstream distinguishes the two.
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import Base, SessionLocal, engine
from app.domain.enums import Market, OrderSide
from app.domain.markets import get_market
from app.models.market import Stock
from app.models.portfolio import Order, Portfolio
from app.models.system import NewsArticle, Watchlist, WatchlistItem
from app.repositories.market_repository import PriceRepository, StockRepository
from app.services.news_service import NewsService
from app.services.portfolio_service import PortfolioService
from scripts.generate_synthetic_data import generate_synthetic_ohlcv

# (symbol, name, sector, base_price, market_cap)
# Market caps are in ₹ crore for India and $ billion for the US — the same unit
# the respective market quotes them in, so the heatmap's relative tile areas are
# meaningful within a market.
INDIA_UNIVERSE = [
    ("RELIANCE",   "Reliance Industries Ltd",         "Energy",                  2830.0, 1_920_000),
    ("TCS",        "Tata Consultancy Services Ltd",   "Information Technology",  3560.0, 1_300_000),
    ("HDFCBANK",   "HDFC Bank Ltd",                   "Financial Services",      1690.0, 1_280_000),
    ("INFY",       "Infosys Ltd",                     "Information Technology",  1510.0,   625_000),
    ("ICICIBANK",  "ICICI Bank Ltd",                  "Financial Services",      1230.0,   865_000),
    ("SBIN",       "State Bank of India",             "Financial Services",       808.0,   721_000),
    ("BHARTIARTL", "Bharti Airtel Ltd",               "Telecommunications",      1445.0,   860_000),
    ("ITC",        "ITC Ltd",                         "Consumer Staples",         437.0,   546_000),
    ("LT",         "Larsen & Toubro Ltd",             "Industrials",             3640.0,   500_000),
    ("KOTAKBANK",  "Kotak Mahindra Bank Ltd",         "Financial Services",      1755.0,   349_000),
    ("AXISBANK",   "Axis Bank Ltd",                   "Financial Services",      1160.0,   358_000),
    ("HINDUNILVR", "Hindustan Unilever Ltd",          "Consumer Staples",        2470.0,   580_000),
    ("MARUTI",     "Maruti Suzuki India Ltd",         "Consumer Discretionary", 12_450.0,  391_000),
    ("SUNPHARMA",  "Sun Pharmaceutical Industries",   "Healthcare",              1785.0,   428_000),
    ("TITAN",      "Titan Company Ltd",               "Consumer Discretionary",  3380.0,   300_000),
    ("WIPRO",      "Wipro Ltd",                       "Information Technology",   542.0,   283_000),
]

US_UNIVERSE = [
    ("AAPL",  "Apple Inc.",                 "Information Technology",  228.5, 3_460),
    ("MSFT",  "Microsoft Corporation",      "Information Technology",  441.2, 3_280),
    ("NVDA",  "NVIDIA Corporation",         "Information Technology",  135.4, 3_330),
    ("GOOGL", "Alphabet Inc.",              "Communication Services",  186.3, 2_290),
    ("AMZN",  "Amazon.com, Inc.",           "Consumer Discretionary",  201.7, 2_110),
    ("META",  "Meta Platforms, Inc.",       "Communication Services",  598.4, 1_510),
    ("TSLA",  "Tesla, Inc.",                "Consumer Discretionary",  345.2, 1_100),
    ("JPM",   "JPMorgan Chase & Co.",       "Financial Services",      248.6,   700),
    ("JNJ",   "Johnson & Johnson",          "Healthcare",              157.9,   380),
    ("XOM",   "Exxon Mobil Corporation",    "Energy",                  118.3,   520),
    ("V",     "Visa Inc.",                  "Financial Services",      312.8,   615),
    ("WMT",   "Walmart Inc.",               "Consumer Staples",         92.4,   745),
    ("UNH",   "UnitedHealth Group Inc.",    "Healthcare",              592.1,   545),
    ("PG",    "Procter & Gamble Company",   "Consumer Staples",        168.7,   397),
]

# Index instruments are seeded as real Stock rows (is_index=True) so they flow
# through the identical price/indicator pipeline as any equity.
INDEX_LEVELS = {
    "NIFTY50": 24_584.0, "SENSEX": 80_457.0, "BANKNIFTY": 52_145.0, "NIFTYIT": 35_645.0,
    "SPX": 5_842.0, "NDX": 20_650.0, "DJI": 43_280.0, "SOX": 5_120.0,
}

# (symbol, quantity) — a deliberately imperfect book: concentrated, spread across
# sectors, so the P&L, allocation and correlation pages all have something real.
INDIA_POSITIONS = [
    ("RELIANCE", 25), ("TCS", 25), ("HDFCBANK", 18),
    ("INFY", 40), ("ICICIBANK", 30), ("ITC", 120), ("SUNPHARMA", 12),
]
US_POSITIONS = [
    ("AAPL", 60), ("MSFT", 25), ("NVDA", 80),
    ("GOOGL", 40), ("AMZN", 30), ("JPM", 20), ("JNJ", 35),
]

NEWS_IN = [
    ("RBI keeps repo rate unchanged, signals continued focus on growth", "Economic Times", "Monetary Policy", None,
     "The Monetary Policy Committee voted to hold the repo rate steady, citing moderating inflation and robust domestic demand."),
    ("Reliance beats quarterly estimates as retail and Jio margins expand", "Business Standard", "Earnings", "RELIANCE",
     "Consolidated revenue rose sharply, with net profit exceeding street expectations on strong operating leverage."),
    ("IT stocks rally as global deal pipeline shows recovery", "Mint", "Sector", "TCS",
     "Large-cap IT names gained after commentary pointed to improving discretionary spending among US clients."),
    ("TCS wins multi-year transformation mandate from European bank", "Moneycontrol", "Contracts", "TCS",
     "The deal strengthens the order book and supports growth guidance for the coming quarters."),
    ("HDFC Bank reports steady loan growth, asset quality stable", "Financial Express", "Earnings", "HDFCBANK",
     "Advances grew in double digits while gross non-performing assets remained flat sequentially."),
    ("Infosys downgraded on margin concerns despite revenue beat", "Reuters India", "Analyst", "INFY",
     "Analysts flagged weakness in operating margins even as revenue exceeded guidance."),
    ("Auto sales slump in festive quarter as rural demand weakens", "Economic Times", "Sector", "MARUTI",
     "Passenger vehicle dispatches declined, with entry-level models seeing the sharpest fall."),
    ("Banking stocks surge as credit growth accelerates", "Mint", "Sector", "ICICIBANK",
     "Private lenders led gains on the back of improving net interest margins."),
    ("ITC announces record dividend after strong FMCG performance", "Business Standard", "Corporate Action", "ITC",
     "The board approved a higher payout, citing robust cash generation across segments."),
    ("Sun Pharma faces regulatory probe over manufacturing practices", "Reuters India", "Regulatory", "SUNPHARMA",
     "The company said it is cooperating fully and does not expect a material impact on supply."),
    ("Nifty closes at record high on sustained foreign inflows", "Moneycontrol", "Markets", None,
     "Benchmark indices extended gains for a fourth straight session as institutional buying continued."),
    ("Crude oil volatility raises input cost concerns for manufacturers", "Financial Express", "Commodities", None,
     "Sharp swings in Brent have made input planning difficult across industrial sectors."),
]

NEWS_US = [
    ("Fed signals patience on rate cuts as inflation cools gradually", "Reuters", "Monetary Policy", None,
     "Officials indicated no urgency to ease policy, pointing to a resilient labour market."),
    ("Nvidia beats on data-centre revenue, raises guidance", "Bloomberg", "Earnings", "NVDA",
     "Quarterly revenue surged well past estimates as AI infrastructure demand accelerated."),
    ("Apple unveils expanded services tier, shares jump", "CNBC", "Product", "AAPL",
     "The announcement was received positively, with analysts raising services revenue forecasts."),
    ("Microsoft cloud growth strong but capex weighs on margins", "WSJ", "Earnings", "MSFT",
     "Azure growth exceeded expectations while heavy infrastructure spending pressured operating margins."),
    ("Tesla deliveries miss estimates amid softer EV demand", "Reuters", "Earnings", "TSLA",
     "Quarterly deliveries fell short of consensus as competition intensified in key markets."),
    ("JPMorgan profit rises on higher net interest income", "Bloomberg", "Earnings", "JPM",
     "The bank reported stronger-than-expected results, helped by resilient consumer credit."),
    ("Amazon expands logistics network, targeting same-day coverage", "CNBC", "Operations", "AMZN",
     "The buildout is expected to lift fulfilment costs near term while improving delivery speed."),
    ("Healthcare stocks decline on policy uncertainty", "WSJ", "Sector", "UNH",
     "Managed care names weakened following commentary on potential reimbursement changes."),
    ("Meta advertising revenue accelerates on AI-driven targeting", "Bloomberg", "Earnings", "META",
     "Ad impressions and pricing both improved, driving a significant revenue beat."),
    ("Energy sector slumps as crude retreats from highs", "Reuters", "Sector", "XOM",
     "Integrated majors fell alongside a broad decline in oil benchmarks."),
    ("S&P 500 notches fresh record as breadth improves", "CNBC", "Markets", None,
     "Gains were broad-based, with advancing issues outpacing decliners by a wide margin."),
    ("Investors rotate into defensives amid volatility concerns", "WSJ", "Markets", None,
     "Staples and utilities outperformed as investors trimmed exposure to high-beta names."),
]

UNIVERSES = {
    Market.INDIA: (INDIA_UNIVERSE, INDIA_POSITIONS, NEWS_IN),
    Market.UNITED_STATES: (US_UNIVERSE, US_POSITIONS, NEWS_US),
}

N_DAYS = 780  # ~3 years of sessions — enough for 52-week ranges and model training


def _upsert_stock(db, symbol, name, market, sector, base_price, market_cap, is_index=False) -> Stock:
    definition = get_market(market)
    repo = StockRepository(db)
    if stock := repo.get_by_symbol(symbol):
        return stock
    return repo.create(Stock(
        symbol=symbol, name=name, exchange=definition.exchange, market=market,
        sector=sector, industry=sector, currency=definition.currency,
        is_index=is_index, market_cap=float(market_cap) if market_cap else None,
    ))


def _seed_prices(db, stock: Stock, base_price: float, *, vol: float, drift: float) -> int:
    df = generate_synthetic_ohlcv(
        symbol=stock.symbol, n_days=N_DAYS, start_price=base_price,
        annual_drift=drift, annual_vol=vol,
        # Deterministic per symbol: re-running the seed reproduces the same
        # history, so screenshots, tests and demos stay stable.
        seed=abs(hash(stock.symbol)) % 100_000,
    )
    bars = df.to_dict("records")
    for bar in bars:
        bar["source"] = "synthetic_seed"
    return PriceRepository(db).bulk_upsert(stock.id, bars)


def seed_market(db, market: Market) -> None:
    definition = get_market(market)
    universe, positions, news_items = UNIVERSES[market]
    print(f"\n=== {definition.name} ({market.value}) ===")

    # 1. Equities + price history
    stocks: dict[str, Stock] = {}
    for symbol, name, sector, base_price, cap in universe:
        stock = _upsert_stock(db, symbol, name, market, sector, base_price, cap)
        stocks[symbol] = stock
        print(f"  {symbol:<11} {_seed_prices(db, stock, base_price, vol=0.26, drift=0.10):>4} bars")

    # 2. Index instruments — lower volatility, as a diversified basket genuinely has
    for index in definition.indices:
        level = INDEX_LEVELS.get(index.symbol, 10_000.0)
        stock = _upsert_stock(db, index.symbol, index.name, market, "Index", level, None, is_index=True)
        print(f"  {index.symbol:<11} {_seed_prices(db, stock, level, vol=0.14, drift=0.09):>4} bars (index)")

    # 3. Portfolio with a real order ledger
    if db.query(Portfolio).filter(Portfolio.market == market).first():
        print("  portfolio already present — skipped")
    else:
        portfolio = Portfolio(
            name=f"{definition.name} Growth Portfolio",
            market=market,
            base_currency=definition.currency,
            benchmark_symbol=definition.benchmark_symbol,
            cash_balance=250_000.0 if market == Market.INDIA else 12_000.0,
            is_default=True,
        )
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)

        service = PortfolioService(db)
        price_repo = PriceRepository(db)
        # Orders are backdated across the last ~18 months so the transactions
        # table and the performance chart have genuine time spread.
        for index, (symbol, quantity) in enumerate(positions):
            stock = stocks[symbol]
            history = price_repo.list_bars(stock.id, limit=400)
            entry = history[max(0, len(history) - 1 - (30 * (index + 3)))]
            service.record_order(portfolio.id, Order(
                stock_id=stock.id, side=OrderSide.BUY, quantity=float(quantity),
                price=round(entry.close, 2),
                transaction_cost=round(entry.close * quantity * 0.0005, 2),
                slippage=round(entry.close * quantity * 0.0002, 2),
                is_simulated=True, notes="Seeded opening position",
                executed_at=entry.timestamp,
            ))

        # One partial exit, so realized P&L is exercised rather than always zero.
        exit_symbol, exit_qty = positions[-1]
        exit_stock = stocks[exit_symbol]
        recent = price_repo.list_bars(exit_stock.id, limit=20)[-1]
        service.record_order(portfolio.id, Order(
            stock_id=exit_stock.id, side=OrderSide.SELL, quantity=float(exit_qty) / 2,
            price=round(recent.close, 2),
            transaction_cost=round(recent.close * exit_qty / 2 * 0.0005, 2),
            slippage=0.0, is_simulated=True, notes="Seeded partial profit-taking",
            executed_at=recent.timestamp,
        ))
        print(f"  portfolio '{portfolio.name}' with {len(positions) + 1} orders")

    # 4. Watchlist
    if db.query(Watchlist).filter(Watchlist.market == market).first():
        print("  watchlist already present — skipped")
    else:
        watchlist = Watchlist(name=f"{definition.name} Watchlist", market=market, is_default=True)
        db.add(watchlist)
        db.commit()
        db.refresh(watchlist)
        for position, (symbol, *_rest) in enumerate(universe[:8]):
            db.add(WatchlistItem(watchlist_id=watchlist.id, stock_id=stocks[symbol].id, position=position))
        db.commit()
        print("  watchlist with 8 symbols")

    # 5. News, scored by the production sentiment engine
    if db.query(NewsArticle).filter(NewsArticle.market == market).count():
        print("  news already present — skipped")
    else:
        news_service = NewsService(db)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for offset, (headline, source, category, symbol, summary) in enumerate(news_items):
            news_service.ingest(
                headline=headline, source=source,
                url=f"https://example.com/news/{market.value.lower()}/{offset + 1}",
                market=market,
                published_at=now - timedelta(hours=offset * 3 + 1),
                summary=summary, stock_symbol=symbol,
                entities=[e for e in (symbol, category) if e],
            )
        print(f"  {len(news_items)} news articles (sentiment scored)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed StockVision Pro with demo data.")
    parser.add_argument("--market", choices=["IN", "US", "ALL"], default="ALL")
    parser.add_argument("--reset", action="store_true", help="Drop every table before seeding.")
    args = parser.parse_args()

    if args.reset:
        print("Dropping all tables ...")
        Base.metadata.drop_all(bind=engine)

    print(f"Creating tables (if missing) on {engine.url} ...")
    Base.metadata.create_all(bind=engine)

    markets = (
        [Market.INDIA, Market.UNITED_STATES] if args.market == "ALL" else [Market(args.market)]
    )

    db = SessionLocal()
    try:
        for market in markets:
            seed_market(db, market)
    finally:
        db.close()

    print(
        "\nSeed complete.\n"
        "  Start the API :  uvicorn app.main:app --reload\n"
        "  API docs      :  http://localhost:8000/docs\n"
        "  Train a model :  python3 scripts/train_model.py --symbol RELIANCE\n"
    )


if __name__ == "__main__":
    main()
