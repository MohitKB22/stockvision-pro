"""
End-to-end API smoke test.

Exercises every endpoint against a seeded database and asserts the contract the
frontend depends on: status codes, the error envelope shape, correlation headers
and the report artifacts.

Runs IN-PROCESS via FastAPI's TestClient rather than against a live server, so CI
needs no sidecar, no port allocation and no readiness polling. The v1 scripts
this replaces (`e2e_smoke_test.py`, `e2e_copilot_test.py`) built an httpx client
at import time and failed at collection if nothing was listening.

    python scripts/seed_data.py --market IN
    python scripts/e2e_api_test.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.core.dependencies import rate_limiter
from app.main import app

app.dependency_overrides[rate_limiter] = lambda: None
client = TestClient(app)

failures: list[tuple[str, int, str]] = []
passed = 0


def check(method: str, url: str, expect: int = 200, **kwargs):
    global passed
    response = getattr(client, method)(url, **kwargs)
    tag = f"{method.upper():6s} {url}"
    if response.status_code != expect:
        failures.append((tag, response.status_code, response.text[:200]))
        print(f"FAIL {tag} -> {response.status_code} (want {expect})")
    else:
        passed += 1
    return response


def main() -> int:
    check("get", "/health")
    check("get", "/health/ready")
    check("get", "/openapi.json")
    check("get", "/api/v1/markets")

    portfolio_id = check("get", "/api/v1/portfolios/default?market=IN").json().get("id")
    watchlist_id = check("get", "/api/v1/watchlists/default?market=IN").json().get("id")

    for url in [
        "/api/v1/market/overview?market=IN", "/api/v1/market/indices?market=IN",
        "/api/v1/market/movers?market=IN", "/api/v1/market/sectors?market=IN",
        "/api/v1/market/heatmap?market=IN", "/api/v1/market/breadth?market=IN",
        "/api/v1/market/52-week?market=IN", "/api/v1/market/session?market=IN",
        "/api/v1/market/quotes?symbols=RELIANCE,TCS", "/api/v1/market/quotes/RELIANCE",
        "/api/v1/market/indices/NIFTY50/constituents?market=IN",
        "/api/v1/stocks?market=IN", "/api/v1/stocks/search?q=rel&market=IN",
        "/api/v1/stocks/sectors?market=IN", "/api/v1/stocks/RELIANCE",
        "/api/v1/stocks/RELIANCE/prices?limit=100", "/api/v1/stocks/RELIANCE/features?limit=60",
        f"/api/v1/portfolios/{portfolio_id}", f"/api/v1/portfolios/{portfolio_id}/summary",
        f"/api/v1/portfolios/{portfolio_id}/performance?days=180",
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        f"/api/v1/portfolios/{portfolio_id}/risk",
        f"/api/v1/portfolios/{portfolio_id}/risk/monte-carlo?n_simulations=200",
        f"/api/v1/portfolios/{portfolio_id}/risk/correlation",
        f"/api/v1/portfolios/{portfolio_id}/risk/stress-test",
        "/api/v1/news?market=IN", "/api/v1/news/sentiment?market=IN",
        "/api/v1/watchlists?market=IN", f"/api/v1/watchlists/{watchlist_id}",
        "/api/v1/documents", "/api/v1/copilot/prompts", "/api/v1/copilot/conversations",
        "/api/v1/copilot/history", "/api/v1/reports", "/api/v1/settings",
        "/api/v1/settings/integrations", "/api/v1/admin/overview", "/api/v1/admin/health",
        "/api/v1/admin/logs", "/api/v1/models", "/api/v1/signals/recent",
        "/api/v1/predictions/RELIANCE/forecast?horizon_days=5",
        "/api/v1/predictions/RELIANCE/history",
    ]:
        check("get", url)

    # --- Mutations -----------------------------------------------------------
    check("post", "/api/v1/signals/RELIANCE")
    check("post", "/api/v1/signals", json={"symbols": ["RELIANCE", "TCS"]})
    check("post", f"/api/v1/portfolios/{portfolio_id}/orders", expect=201,
          json={"symbol": "WIPRO", "side": "buy", "quantity": 10, "price": 540.0})
    check("post", f"/api/v1/portfolios/{portfolio_id}/orders", expect=400,
          json={"symbol": "WIPRO", "side": "sell", "quantity": 9999, "price": 540.0})
    check("post", f"/api/v1/watchlists/{watchlist_id}/items", expect=201, json={"symbol": "MARUTI"})
    check("post", f"/api/v1/watchlists/{watchlist_id}/items", expect=409, json={"symbol": "MARUTI"})
    check("delete", f"/api/v1/watchlists/{watchlist_id}/items/MARUTI")
    check("patch", "/api/v1/settings", json={"theme": "midnight"})
    check("post", "/api/v1/settings/reset")

    conversation = check("post", "/api/v1/copilot/conversations", expect=201, json={"title": "E2E"}).json()
    check("get", f"/api/v1/copilot/conversations/{conversation['id']}")
    check("delete", f"/api/v1/copilot/conversations/{conversation['id']}")

    # --- Reports: all four types in all three formats ------------------------
    for report_type in ("portfolio", "risk", "prediction", "tax"):
        for report_format in ("pdf", "csv", "excel"):
            report = check("post", "/api/v1/reports/generate", expect=201, json={
                "report_type": report_type,
                "report_format": report_format,
                "portfolio_id": portfolio_id,
            })
            if report.status_code == 201:
                download = check("get", f"/api/v1/reports/{report.json()['id']}/download")
                assert len(download.content) > 200, f"{report_type}/{report_format} artifact is empty"

    # --- Contract assertions --------------------------------------------------
    response = check("get", "/api/v1/stocks/NOPE", expect=404)
    assert set(response.json()["error"]) >= {"code", "message", "status"}, response.text

    response = check("get", "/api/v1/definitely-not-a-route", expect=404)
    assert response.json()["error"]["code"] == "not_found", response.text

    response = check("post", "/api/v1/portfolios", expect=422, json={"name": ""})
    assert response.json()["error"]["code"] == "validation_error", response.text
    assert response.json()["error"]["context"]["fields"], response.text

    response = check("post", "/api/v1/copilot/query", expect=422, json={"question": "revenue?"})
    assert response.json()["error"]["code"] == "insufficient_data", response.text

    headers = client.get("/health", headers={"X-Request-ID": "e2e-trace"}).headers
    assert headers["X-Request-ID"] == "e2e-trace", "inbound correlation ID must be preserved"
    assert headers["X-Content-Type-Options"] == "nosniff", "security headers must be present"

    assert client.get("/api/v1/stocks?limit=99999").status_code == 422, "limit must be capped"

    print(f"\n=== {passed} passed, {len(failures)} failed ===")
    for failure in failures:
        print("  ", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
