#!/usr/bin/env python3
"""
Smoke test for a RUNNING deployment, over real HTTP.

Unlike scripts/e2e_api_test.py (in-process, against a local database), this hits
a live base URL — a local uvicorn or the hosted API — and exercises what each
page of the UI depends on: market data for both markets, portfolio analytics and
the risk engine, news, watchlists, settings and admin, AI signals, a real model
train -> predict round trip (SHAP attributions included), and a report
generate -> download round trip. It also checks the CORS headers the browser
needs and, optionally, that the frontend serves the app.

Standard library only, so it runs anywhere:

    python scripts/smoke_test.py https://api.example.com
    python scripts/smoke_test.py https://api.example.com \
        --origin https://app.example.com --frontend https://app.example.com

It writes a little demo state (signals, one small model version, one report),
exactly as a visitor clicking through the app would. Exit code 0 = all passed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

TIMEOUT = 290  # training is synchronous; first requests may also hit a cold start


class Smoke:
    def __init__(self, base: str, origin: str | None) -> None:
        self.base = base.rstrip("/")
        self.origin = origin
        self.passed = 0
        self.failures: list[str] = []

    def call(self, method: str, path: str, body=None, accept="application/json"):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Accept", accept)
        request.add_header("User-Agent", "stockvision-smoke-test/1.0")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if self.origin:
            request.add_header("Origin", self.origin)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return response.status, dict(response.headers), response.read(), time.perf_counter() - started
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read(), time.perf_counter() - started

    def check(self, name, method, path, *, expect=200, body=None, validate=None, accept="application/json"):
        try:
            status, headers, raw, elapsed = self.call(method, path, body, accept)
        except Exception as exc:  # network failure is a failed check, not a crash
            return self._fail(name, f"{type(exc).__name__}: {exc}")
        if status != expect:
            return self._fail(name, f"HTTP {status} (expected {expect}): {raw[:240]!r}")
        payload = raw
        if "json" in headers.get("content-type", headers.get("Content-Type", "")):
            payload = json.loads(raw or b"null")
        if self.origin and path.startswith("/api/"):
            allowed = {k.lower(): v for k, v in headers.items()}.get("access-control-allow-origin")
            if allowed not in (self.origin, "*"):
                return self._fail(name, f"CORS: Access-Control-Allow-Origin={allowed!r} for {self.origin}")
        if validate is not None:
            try:
                problem = validate(payload)
            except Exception as exc:
                problem = f"validator raised {type(exc).__name__}: {exc}"
            if problem:
                return self._fail(name, problem)
        self.passed += 1
        print(f"  ok    {name:<46} {elapsed * 1000:8.0f} ms")
        return payload

    def _fail(self, name, reason):
        self.failures.append(f"{name}: {reason}")
        print(f"  FAIL  {name:<46} {reason}")
        return None


def nonempty(key=None):
    def validate(payload):
        value = payload if key is None else payload.get(key)
        return None if value else f"{key or 'response'} is empty"
    return validate


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test a running StockVision Pro API")
    parser.add_argument("base_url", help="API origin, e.g. https://api.example.com (no /api/v1)")
    parser.add_argument("--origin", help="frontend origin whose CORS access must be granted")
    parser.add_argument("--frontend", help="frontend URL that must serve the app")
    args = parser.parse_args()
    s = Smoke(args.base_url, args.origin)
    api = "/api/v1"
    print(f"Smoke testing {s.base}")

    s.check("liveness", "GET", "/health")
    s.check("readiness (database connected)", "GET", "/health/ready",
            validate=lambda p: None if p.get("database") == "connected" else f"{p}")
    s.check("markets", "GET", f"{api}/markets", validate=nonempty())

    for market, symbol in (("IN", "RELIANCE"), ("US", "AAPL")):
        s.check(f"market overview {market}", "GET", f"{api}/market/overview?market={market}")
        s.check(f"movers {market}", "GET", f"{api}/market/movers?market={market}")
        s.check(f"heatmap {market}", "GET", f"{api}/market/heatmap?market={market}")
        s.check(f"stock list {market}", "GET", f"{api}/stocks?market={market}", validate=nonempty())
        s.check(f"price history {symbol}", "GET", f"{api}/stocks/{symbol}/prices?limit=120", validate=nonempty())
        s.check(f"indicators {symbol}", "GET", f"{api}/stocks/{symbol}/features?limit=60")

    portfolio = s.check("default portfolio", "GET", f"{api}/portfolios/default?market=IN")
    if portfolio:
        pid = portfolio["id"]
        s.check("portfolio summary", "GET", f"{api}/portfolios/{pid}/summary", validate=nonempty("holdings"))
        s.check("portfolio performance", "GET", f"{api}/portfolios/{pid}/performance?days=180", validate=nonempty())
        s.check("risk metrics (VaR/ES/Sharpe)", "GET", f"{api}/portfolios/{pid}/risk")
        s.check("Monte Carlo", "GET", f"{api}/portfolios/{pid}/risk/monte-carlo?n_simulations=200")
        s.check("correlation matrix", "GET", f"{api}/portfolios/{pid}/risk/correlation")
        s.check("stress scenarios", "GET", f"{api}/portfolios/{pid}/risk/stress-test")

    s.check("news + sentiment", "GET", f"{api}/news?market=IN", validate=nonempty("items"))
    s.check("market sentiment", "GET", f"{api}/news/sentiment?market=IN")
    s.check("watchlist", "GET", f"{api}/watchlists/default?market=IN")
    s.check("settings", "GET", f"{api}/settings")
    s.check("integrations", "GET", f"{api}/settings/integrations")
    s.check("admin overview", "GET", f"{api}/admin/overview")
    s.check("admin health", "GET", f"{api}/admin/health")

    s.check("AI signal (indicators + model)", "POST", f"{api}/signals/RELIANCE",
            validate=lambda p: None if p.get("action") in ("BUY", "SELL", "HOLD", "buy", "sell", "hold") else f"{p}")
    trained = s.check("train model (XGBoost, Optuna, walk-forward)", "POST", f"{api}/models/train",
                      body={"symbol": "RELIANCE", "n_optuna_trials": 3, "n_walk_forward_splits": 3})
    if trained:
        s.check("predict with SHAP attributions", "POST", f"{api}/predictions", body={"symbol": "RELIANCE"},
                validate=nonempty("shap_contributions"))
    s.check("forecast", "GET", f"{api}/predictions/RELIANCE/forecast?horizon_days=5")

    report = s.check("generate report (CSV)", "POST", f"{api}/reports/generate", expect=201,
                     body={"report_type": "prediction", "report_format": "csv"})
    if report:
        s.check("download report", "GET", f"{api}/reports/{report['id']}/download", accept="*/*",
                validate=lambda p: None if len(p) == report["size_bytes"] else "size mismatch")
    s.check("unknown route -> JSON 404", "GET", f"{api}/definitely-not-a-route", expect=404,
            validate=lambda p: None if p["error"]["code"] == "not_found" else f"{p}")
    s.check("API docs", "GET", "/docs", accept="text/html",
            validate=lambda p: None if b"swagger" in p.lower() else "not the Swagger page")

    if args.frontend:
        frontend = Smoke(args.frontend, None)
        for path in ("/", "/dashboard", "/prediction", "/stocks/RELIANCE"):
            result = frontend.check(f"frontend {path}", "GET", path, accept="text/html",
                                    validate=lambda p: None if b"StockVision" in p else "app shell missing")
            if result is not None:
                s.passed += 1
            else:
                s.failures.extend(frontend.failures[-1:])

    print(f"\n{s.passed} passed, {len(s.failures)} failed")
    for failure in s.failures:
        print(f"  - {failure}")
    return 0 if not s.failures else 1


if __name__ == "__main__":
    sys.exit(main())
