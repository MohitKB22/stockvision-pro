"""
API tests for market data, ML/signals, portfolio analytics and the platform
endpoints.

CHANGE LOG (v2.0): every RBAC test is gone — there are no roles to enforce. They
are replaced by tests for the things that DO still constrain the API: the standard
error envelope, input validation, idempotent imports, the symbol-scoped model
lookup, the sell-more-than-held guard and realized P&L.
"""
from scripts.generate_synthetic_data import generate_synthetic_ohlcv


def _register_stock_with_prices(client, symbol="DEMO", n_days=300, market="IN"):
    client.post("/api/v1/stocks", json={
        "symbol": symbol, "name": f"{symbol} Corp", "exchange": "NSE",
        "market": market, "sector": "Technology", "currency": "INR", "market_cap": 100_000,
    })
    df = generate_synthetic_ohlcv(symbol=symbol, n_days=n_days, seed=11)
    bars = [
        {"timestamp": row.timestamp.isoformat(), "open": row.open, "high": row.high,
         "low": row.low, "close": row.close, "volume": row.volume}
        for row in df.itertuples()
    ]
    assert client.post(f"/api/v1/stocks/{symbol}/prices", json={"bars": bars}).status_code == 201
    return df


class TestStocksAPI:
    def test_create_and_get_stock(self, client):
        create = client.post("/api/v1/stocks", json={
            "symbol": "aapl", "name": "Apple Inc.", "exchange": "NASDAQ",
            "market": "US", "sector": "Technology", "currency": "USD",
        })
        assert create.status_code == 201
        # Symbols are normalized to uppercase server-side, so lookups are
        # case-insensitive without every caller remembering to upper().
        assert create.json()["symbol"] == "AAPL"

        fetched = client.get("/api/v1/stocks/aapl")
        assert fetched.status_code == 200
        assert fetched.json()["name"] == "Apple Inc."

    def test_duplicate_symbol_returns_409_with_error_code(self, client):
        payload = {"symbol": "DUP", "name": "Dup", "exchange": "NSE", "market": "IN"}
        client.post("/api/v1/stocks", json=payload)
        response = client.post("/api/v1/stocks", json=payload)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "already_exists"

    def test_unknown_stock_returns_404_with_error_envelope(self, client):
        response = client.get("/api/v1/stocks/NOSUCHTICKER")
        assert response.status_code == 404
        error = response.json()["error"]
        assert error["code"] == "not_found"
        assert set(error) >= {"code", "message", "status"}

    def test_no_authentication_is_required(self, client):
        """v1 returned 401 here. The platform is unauthenticated by design now, and
        this test exists so a reintroduced auth guard fails loudly."""
        assert client.get("/api/v1/stocks").status_code == 200

    def test_bulk_price_import_is_idempotent(self, client):
        df = _register_stock_with_prices(client, symbol="IDEM", n_days=50)
        bars = [
            {"timestamp": row.timestamp.isoformat(), "open": row.open, "high": row.high,
             "low": row.low, "close": row.close, "volume": row.volume}
            for row in df.itertuples()
        ]
        second = client.post("/api/v1/stocks/IDEM/prices", json={"bars": bars})
        assert second.json()["bars_inserted"] == 0
        assert second.json()["duplicates_skipped"] == len(bars)

    def test_features_endpoint_returns_indicator_set(self, client):
        _register_stock_with_prices(client, symbol="FEAT", n_days=120)
        response = client.get("/api/v1/stocks/FEAT/features?limit=60")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 60
        assert {"rsi_14", "macd", "atr_14"} <= set(body[-1]["indicators"])

    def test_search_matches_symbol_and_name(self, client):
        _register_stock_with_prices(client, symbol="SRCH", n_days=30)
        assert any(s["symbol"] == "SRCH" for s in client.get("/api/v1/stocks/search?q=srch").json())
        assert any(s["symbol"] == "SRCH" for s in client.get("/api/v1/stocks/search?q=corp").json())

    def test_pagination_limit_is_capped(self, client):
        """An uncapped `limit` is a trivial denial-of-service vector."""
        assert client.get("/api/v1/stocks?limit=100000").status_code == 422


class TestMarketOverviewAPI:
    def test_overview_is_computed_from_stored_prices(self, client):
        _register_stock_with_prices(client, symbol="OVR1", n_days=300)
        _register_stock_with_prices(client, symbol="OVR2", n_days=300)

        response = client.get("/api/v1/market/overview?market=IN")
        assert response.status_code == 200
        body = response.json()
        assert body["currency_symbol"] == "₹"
        breadth = body["breadth"]
        assert breadth["total"] == 2
        assert breadth["advancers"] + breadth["decliners"] + breadth["unchanged"] == 2

    def test_symbols_without_two_bars_are_omitted_not_faked(self, client):
        """A stock with no computable change must be ABSENT, never shown as 0.00%."""
        client.post("/api/v1/stocks", json={
            "symbol": "BARE", "name": "Bare", "exchange": "NSE", "market": "IN",
        })
        assert client.get("/api/v1/market/breadth?market=IN").json()["total"] == 0

    def test_markets_registry_is_served(self, client):
        markets = client.get("/api/v1/markets").json()
        assert {m["code"] for m in markets} == {"IN", "US"}
        india = next(m for m in markets if m["code"] == "IN")
        assert india["digit_grouping"] == "indian"
        assert india["currency_symbol"] == "₹"
        assert any(i["symbol"] == "NIFTY50" for i in india["indices"])

    def test_session_status_does_not_claim_holiday_awareness(self, client):
        body = client.get("/api/v1/market/session?market=IN").json()
        assert body["holiday_calendar_applied"] is False
        assert body["timezone"] == "Asia/Kolkata"


class TestMLAndSignalAPI:
    def test_full_train_predict_signal_flow(self, client):
        _register_stock_with_prices(client, symbol="MLCO", n_days=400)

        train = client.post("/api/v1/models/train", json={
            "symbol": "MLCO", "task": "trend_classification", "algorithm": "lightgbm",
            "n_optuna_trials": 3, "n_walk_forward_splits": 3,
        })
        assert train.status_code == 200
        body = train.json()
        assert body["stage"] == "production"  # first model for this symbol+task auto-promotes
        assert 0 <= body["metrics"]["accuracy"] <= 1
        assert body["top_features"]

        prediction = client.post("/api/v1/predictions", json={"symbol": "MLCO"})
        assert prediction.status_code == 200
        assert 0 <= prediction.json()["predicted_value"] <= 1
        assert prediction.json()["shap_contributions"]

        signal = client.post("/api/v1/signals/MLCO")
        assert signal.status_code == 200
        assert signal.json()["action"] in {"strong_buy", "buy", "hold", "sell", "strong_sell"}

    def test_a_models_predictions_are_scoped_to_its_own_symbol(self, client):
        """
        Regression test for the most serious defect fixed in v2.0: the
        production-model lookup was scoped by task only, so a model trained on one
        symbol silently served predictions for a completely different one.
        """
        _register_stock_with_prices(client, symbol="TRAINED", n_days=400)
        _register_stock_with_prices(client, symbol="UNTRAINED", n_days=400)

        client.post("/api/v1/models/train", json={
            "symbol": "TRAINED", "task": "trend_classification", "algorithm": "lightgbm",
            "n_optuna_trials": 2, "n_walk_forward_splits": 3,
        })

        assert client.post("/api/v1/predictions", json={"symbol": "TRAINED"}).status_code == 200

        leaked = client.post("/api/v1/predictions", json={"symbol": "UNTRAINED"})
        assert leaked.status_code == 422
        assert leaked.json()["error"]["code"] == "model_not_trained"

    def test_prediction_without_trained_model_returns_422(self, client):
        _register_stock_with_prices(client, symbol="NOMODEL", n_days=100)
        response = client.post("/api/v1/predictions", json={"symbol": "NOMODEL"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "model_not_trained"

    def test_signal_degrades_gracefully_without_a_trained_model(self, client):
        _register_stock_with_prices(client, symbol="NOMODEL2", n_days=100)
        response = client.post("/api/v1/signals/NOMODEL2")
        assert response.status_code == 200
        assert response.json()["action"] in {"strong_buy", "buy", "hold", "sell", "strong_sell"}

    def test_bulk_signal_generation_skips_failures_instead_of_failing_the_batch(self, client):
        _register_stock_with_prices(client, symbol="BULK1", n_days=120)
        response = client.post("/api/v1/signals", json={"symbols": ["BULK1", "DOESNOTEXIST"]})
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_training_with_insufficient_history_returns_422(self, client):
        client.post("/api/v1/stocks", json={
            "symbol": "TINY", "name": "Tiny", "exchange": "NSE", "market": "IN",
        })
        df = generate_synthetic_ohlcv(symbol="TINY", n_days=20, seed=3)
        client.post("/api/v1/stocks/TINY/prices", json={"bars": [
            {"timestamp": row.timestamp.isoformat(), "open": row.open, "high": row.high,
             "low": row.low, "close": row.close, "volume": row.volume}
            for row in df.itertuples()
        ]})
        response = client.post("/api/v1/models/train", json={
            "symbol": "TINY", "task": "trend_classification", "algorithm": "xgboost",
        })
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "insufficient_data"

    def test_forecast_declares_whether_a_model_informed_it(self, client):
        _register_stock_with_prices(client, symbol="FCAST", n_days=200)
        body = client.get("/api/v1/predictions/FCAST/forecast?horizon_days=5").json()
        assert body["model_informed"] is False   # no model trained for this symbol
        assert body["probability_up"] is None
        assert len(body["forecast"]) == 5
        # The 95% band must widen with the horizon — a constant band would mean
        # the sqrt(t) scaling was dropped.
        first, last = body["forecast"][0], body["forecast"][-1]
        assert (last["upper"] - last["lower"]) > (first["upper"] - first["lower"])

    def test_recent_signals_route_is_not_shadowed_by_the_symbol_route(self, client):
        """`/signals/recent` must not be parsed as `/signals/{symbol}` with
        symbol="recent" — route registration order guarantees this."""
        assert client.get("/api/v1/signals/recent").status_code == 200


class TestPortfolioAPI:
    def _portfolio(self, client, name="Test Portfolio"):
        response = client.post("/api/v1/portfolios", json={"name": name, "market": "IN"})
        assert response.status_code == 201
        return response.json()["id"]

    def test_create_place_orders_and_get_summary(self, client):
        _register_stock_with_prices(client, symbol="PORT", n_days=100)
        portfolio_id = self._portfolio(client)

        order = client.post(f"/api/v1/portfolios/{portfolio_id}/orders", json={
            "symbol": "PORT", "side": "buy", "quantity": 10, "price": 100.0,
        })
        assert order.status_code == 201

        summary = client.get(f"/api/v1/portfolios/{portfolio_id}/summary").json()
        assert summary["holdings"][0]["quantity"] == 10
        assert summary["holding_count"] == 1
        assert summary["asset_allocation"]

    def test_first_portfolio_for_a_market_becomes_the_default(self, client):
        portfolio_id = self._portfolio(client, "First")
        assert client.get("/api/v1/portfolios/default?market=IN").json()["id"] == portfolio_id

    def test_selling_more_than_held_is_rejected(self, client):
        """v1 accepted this and produced a negative position that every downstream
        weight calculation then divided by."""
        _register_stock_with_prices(client, symbol="OVERSELL", n_days=60)
        portfolio_id = self._portfolio(client)
        client.post(f"/api/v1/portfolios/{portfolio_id}/orders", json={
            "symbol": "OVERSELL", "side": "buy", "quantity": 5, "price": 10.0,
        })
        response = client.post(f"/api/v1/portfolios/{portfolio_id}/orders", json={
            "symbol": "OVERSELL", "side": "sell", "quantity": 50, "price": 12.0,
        })
        assert response.status_code == 400
        assert response.json()["error"]["context"]["available_quantity"] == 5

    def test_realized_pnl_is_booked_on_a_partial_sell(self, client):
        """v1 discarded realized P&L entirely, understating total return for any
        portfolio that had taken profit."""
        _register_stock_with_prices(client, symbol="REAL", n_days=60)
        portfolio_id = self._portfolio(client)
        client.post(f"/api/v1/portfolios/{portfolio_id}/orders",
                    json={"symbol": "REAL", "side": "buy", "quantity": 10, "price": 100.0})
        client.post(f"/api/v1/portfolios/{portfolio_id}/orders",
                    json={"symbol": "REAL", "side": "sell", "quantity": 4, "price": 150.0})

        summary = client.get(f"/api/v1/portfolios/{portfolio_id}/summary").json()
        assert summary["holdings"][0]["quantity"] == 6
        assert summary["total_realized_pnl"] == 200.0  # 4 units x (150 - 100)

    def test_transactions_ledger_records_every_order(self, client):
        _register_stock_with_prices(client, symbol="LEDGER", n_days=60)
        portfolio_id = self._portfolio(client)
        for _ in range(3):
            client.post(f"/api/v1/portfolios/{portfolio_id}/orders",
                        json={"symbol": "LEDGER", "side": "buy", "quantity": 1, "price": 10.0})
        assert len(client.get(f"/api/v1/portfolios/{portfolio_id}/transactions").json()) == 3

    def test_deleting_a_portfolio_cascades_to_its_holdings(self, client):
        """Requires SQLite foreign keys to be ON — see app/core/database.py. This
        test would have passed vacuously in v1 because the PRAGMA was never set."""
        from app.models.portfolio import PortfolioHolding

        _register_stock_with_prices(client, symbol="CASCADE", n_days=60)
        portfolio_id = self._portfolio(client)
        client.post(f"/api/v1/portfolios/{portfolio_id}/orders",
                    json={"symbol": "CASCADE", "side": "buy", "quantity": 5, "price": 10.0})

        assert client.delete(f"/api/v1/portfolios/{portfolio_id}").status_code == 200
        from app.core.database import get_db  # noqa: F401 — session comes from the override
        # The holdings row must be gone, not orphaned.
        remaining = client.get(f"/api/v1/portfolios/{portfolio_id}/summary")
        assert remaining.status_code == 404
        assert PortfolioHolding is not None

    def test_risk_metrics_require_holdings(self, client):
        portfolio_id = self._portfolio(client, "Empty")
        response = client.get(f"/api/v1/portfolios/{portfolio_id}/risk")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "insufficient_data"

    def test_monte_carlo_is_deterministic_for_the_same_inputs(self, client):
        """A risk figure that changes on every refresh is not a risk figure."""
        _register_stock_with_prices(client, symbol="MC", n_days=300)
        portfolio_id = self._portfolio(client)
        client.post(f"/api/v1/portfolios/{portfolio_id}/orders",
                    json={"symbol": "MC", "side": "buy", "quantity": 10, "price": 100.0})

        url = f"/api/v1/portfolios/{portfolio_id}/risk/monte-carlo?n_simulations=300&horizon_days=60"
        assert client.get(url).json()["terminal"] == client.get(url).json()["terminal"]

    def test_stress_test_declares_when_beta_was_assumed(self, client):
        _register_stock_with_prices(client, symbol="STRESS", n_days=300)
        portfolio_id = self._portfolio(client)
        client.post(f"/api/v1/portfolios/{portfolio_id}/orders",
                    json={"symbol": "STRESS", "side": "buy", "quantity": 10, "price": 100.0})

        scenarios = client.get(f"/api/v1/portfolios/{portfolio_id}/risk/stress-test").json()["scenarios"]
        # No NIFTY50 instrument exists in this test DB, so beta is not computable
        # and the response must SAY it assumed 1.0 rather than implying it knew.
        assert scenarios and all(s["beta_assumed"] is True for s in scenarios)
        assert all(s["beta_used"] == 1.0 for s in scenarios)

    def test_default_portfolio_returns_a_typed_empty_state(self, client):
        response = client.get("/api/v1/portfolios/default?market=IN")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "no_portfolio"


class TestPlatformAPI:
    def test_settings_always_return_a_complete_object(self, client):
        body = client.get("/api/v1/settings").json()
        assert body["theme"] == "dark"
        assert body["default_market"] in {"IN", "US"}

    def test_settings_patch_persists_and_ignores_unknown_keys(self, client):
        client.patch("/api/v1/settings", json={"theme": "midnight"})
        assert client.get("/api/v1/settings").json()["theme"] == "midnight"
        # An unknown key must be dropped, not accumulated in the stored blob.
        client.patch("/api/v1/settings", json={"not_a_setting": True})
        assert "not_a_setting" not in client.get("/api/v1/settings").json()

    def test_settings_reject_invalid_enum_values(self, client):
        assert client.patch("/api/v1/settings", json={"theme": "neon"}).status_code == 422

    def test_integration_status_never_leaks_key_material(self, client):
        body = client.get("/api/v1/settings/integrations").json()
        # Status only — never the key, not even masked (a masked key still leaks
        # length and prefix).
        assert all(set(row) == {"provider", "label", "configured", "description"} for row in body)
        assert all(isinstance(row["configured"], bool) for row in body)

    def test_watchlist_is_created_on_first_read(self, client):
        """A fresh database must not produce an empty state the UI cannot escape."""
        body = client.get("/api/v1/watchlists/default?market=IN").json()
        assert body["is_default"] is True
        assert body["items"] == []

    def test_duplicate_watchlist_symbol_is_rejected(self, client):
        _register_stock_with_prices(client, symbol="WATCH", n_days=40)
        watchlist_id = client.get("/api/v1/watchlists/default?market=IN").json()["id"]
        assert client.post(f"/api/v1/watchlists/{watchlist_id}/items",
                           json={"symbol": "WATCH"}).status_code == 201
        assert client.post(f"/api/v1/watchlists/{watchlist_id}/items",
                           json={"symbol": "WATCH"}).status_code == 409

    def test_watchlist_alert_only_triggers_with_a_real_quote(self, client):
        _register_stock_with_prices(client, symbol="ALERT", n_days=40)
        watchlist_id = client.get("/api/v1/watchlists/default?market=IN").json()["id"]
        body = client.post(f"/api/v1/watchlists/{watchlist_id}/items",
                           json={"symbol": "ALERT", "alert_above": 0.01}).json()
        item = body["items"][0]
        assert item["quote"] is not None
        assert item["alert_triggered"] is True

    def test_admin_overview_counts_real_records(self, client):
        _register_stock_with_prices(client, symbol="ADMIN1", n_days=40)
        body = client.get("/api/v1/admin/overview").json()
        assert body["data_counts"]["stocks"] == 1
        assert body["data_counts"]["price_bars"] == 40
        assert body["health"]["database_connected"] is True
        # Redis is reported as configured, never as verified-connected.
        assert "redis_configured" in body["health"]

    def test_admin_change_pct_is_null_not_zero_without_a_prior_window(self, client):
        cards = {c["key"]: c for c in client.get("/api/v1/admin/overview").json()["cards"]}
        assert cards["predictions"]["change_pct"] is None

    def test_news_feed_names_its_sentiment_engine(self, client):
        body = client.get("/api/v1/news?market=IN").json()
        assert body["summary"]["engine"] == "lexicon_v1"

    def test_validation_errors_carry_field_details(self, client):
        response = client.post("/api/v1/portfolios", json={"name": ""})
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert error["context"]["fields"][0]["field"] == "name"

    def test_unknown_route_uses_the_standard_error_envelope(self, client):
        response = client.get("/api/v1/definitely-not-a-route")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_every_response_carries_a_correlation_id(self, client):
        response = client.get("/health")
        assert response.headers["X-Request-ID"]
        assert float(response.headers["X-Response-Time-ms"]) >= 0

    def test_inbound_request_id_is_preserved(self, client):
        """A trace started at the edge must survive into the application."""
        response = client.get("/health", headers={"X-Request-ID": "edge-trace-123"})
        assert response.headers["X-Request-ID"] == "edge-trace-123"

    def test_security_headers_are_present(self, client):
        headers = client.get("/health").headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert "strict-origin" in headers["Referrer-Policy"]
