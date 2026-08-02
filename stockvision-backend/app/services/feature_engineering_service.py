
from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientDataException, NotFoundException
from app.ml.indicators import FEATURE_COLUMNS, build_feature_matrix
from app.repositories.market_repository import PriceRepository, StockRepository
from app.schemas.market import FeatureSnapshot


class FeatureEngineeringService:
    def __init__(self, db: Session):
        self.db = db
        self.stocks = StockRepository(db)
        self.prices = PriceRepository(db)

    def compute_features(self, symbol: str, limit: int = 200) -> list[FeatureSnapshot]:
        stock = self.stocks.get_by_symbol(symbol)
        if not stock:
            raise NotFoundException(f"Stock {symbol} not found")

        df = self.prices.get_price_series(stock.id, limit=limit)
        if df.empty:
            raise InsufficientDataException(f"No historical price data loaded for {symbol}")

        feat = build_feature_matrix(df)
        snapshots = []
        for _, row in feat.iterrows():
            indicators = {col: (None if pd_isna(row[col]) else float(row[col])) for col in FEATURE_COLUMNS}
            snapshots.append(
                FeatureSnapshot(timestamp=row["timestamp"], close=float(row["close"]), indicators=indicators)
            )
        return snapshots


def pd_isna(value) -> bool:
    """Local import-free NaN check so this module doesn't need to import
    pandas solely for one call site."""
    return value != value  # NaN is the only float that is not equal to itself
