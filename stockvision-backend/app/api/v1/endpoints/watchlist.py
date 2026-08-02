"""Watchlist endpoints — new in v2.0."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import MarketDep
from app.schemas.common import OperationResult
from app.schemas.watchlist import WatchlistCreate, WatchlistItemCreate, WatchlistPublic
from app.services.watchlist_service import WatchlistService

router = APIRouter(prefix="/watchlists", tags=["Watchlist"])


@router.get("", response_model=list[WatchlistPublic], summary="All watchlists for a market")
def list_watchlists(market: MarketDep, db: Session = Depends(get_db)):
    """A default watchlist is created on first read, so this never returns an
    empty list the UI has no way to escape from."""
    return WatchlistService(db).list_all(market)


@router.get("/default", response_model=WatchlistPublic, summary="Default watchlist with live quotes")
def default_watchlist(market: MarketDep, db: Session = Depends(get_db)):
    return WatchlistService(db).get_default(market)


@router.post("", response_model=WatchlistPublic, status_code=201, summary="Create a watchlist")
def create_watchlist(payload: WatchlistCreate, db: Session = Depends(get_db)):
    return WatchlistService(db).create(payload.name, payload.market)


@router.get("/{watchlist_id}", response_model=WatchlistPublic, summary="Watchlist detail")
def get_watchlist(watchlist_id: uuid.UUID, db: Session = Depends(get_db)):
    return WatchlistService(db).get(watchlist_id)


@router.delete("/{watchlist_id}", response_model=OperationResult, summary="Delete a watchlist")
def delete_watchlist(watchlist_id: uuid.UUID, db: Session = Depends(get_db)):
    WatchlistService(db).delete(watchlist_id)
    return OperationResult(message="Watchlist deleted.", id=str(watchlist_id))


@router.post("/{watchlist_id}/items", response_model=WatchlistPublic, status_code=201,
             summary="Add a symbol")
def add_item(watchlist_id: uuid.UUID, payload: WatchlistItemCreate, db: Session = Depends(get_db)):
    return WatchlistService(db).add_symbol(
        watchlist_id, payload.symbol,
        alert_above=payload.alert_above, alert_below=payload.alert_below,
    )


@router.delete("/{watchlist_id}/items/{symbol}", response_model=WatchlistPublic,
               summary="Remove a symbol")
def remove_item(watchlist_id: uuid.UUID, symbol: str, db: Session = Depends(get_db)):
    return WatchlistService(db).remove_symbol(watchlist_id, symbol)
