"""
Behaviour that only matters once the API leaves a laptop: hosted Postgres
connection strings, database-backed file storage for serverless hosts, the
UTC timestamp contract across dialects, and the guards a public, unauthenticated
deployment needs (training budget, upload ceiling, IP anonymization).
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core import storage
from app.core.config import Settings, normalize_database_url, settings
from app.core.middleware import anonymize_ip


@pytest.fixture()
def database_storage(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "database")
    yield
    from app.ml.registry import clear_artifact_cache

    clear_artifact_cache()


# --- configuration ------------------------------------------------------------
@pytest.mark.parametrize(("raw", "expected"), [
    ("postgres://u:p@host/db", "postgresql://u:p@host/db"),
    ("postgresql://u:p@host/db?sslmode=require", "postgresql://u:p@host/db?sslmode=require"),
    ("postgres://u:p@h/db?sslmode=require&pgbouncer=true", "postgresql://u:p@h/db?sslmode=require"),
    ("postgres://u:p@h/db?pgbouncer=true", "postgresql://u:p@h/db"),
    ("  sqlite:///./x.db ", "sqlite:///./x.db"),
])
def test_provider_connection_strings_are_normalized(raw, expected):
    assert normalize_database_url(raw) == expected


def test_integration_variable_is_used_when_database_url_is_unset(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_URL", "postgres://u:p@ep-x-pooler.aws.neon.tech/neondb?sslmode=require")
    assert Settings(_env_file=None).DATABASE_URL == "postgresql://u:p@ep-x-pooler.aws.neon.tech/neondb?sslmode=require"


def test_explicit_database_url_wins(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://a:b@primary/db")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://c:d@other/db")
    assert Settings(_env_file=None).DATABASE_URL == "postgresql://a:b@primary/db"


@pytest.mark.parametrize(("raw", "expected"), [
    ("https://a.example", ["https://a.example"]),
    ("https://a.example, https://b.example", ["https://a.example", "https://b.example"]),
    ('["https://a.example","https://b.example"]', ["https://a.example", "https://b.example"]),
])
def test_cors_origins_from_a_real_environment_variable(monkeypatch, raw, expected):
    """Regression: these crashed at import with SettingsError when they came from
    the environment (pydantic-settings decoded them as JSON first)."""
    monkeypatch.setenv("CORS_ORIGINS", raw)
    assert expected == Settings(_env_file=None).CORS_ORIGINS


def test_serverless_defaults(monkeypatch):
    """Simulates Vercel: the flags are computed at import, so reload the module."""
    import importlib

    import app.core.config as config_module

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))
    try:
        reloaded = importlib.reload(config_module)
        s = reloaded.Settings(_env_file=None)
        assert s.STORAGE_BACKEND == "database"
        assert s.MAX_UPLOAD_BYTES == reloaded.SERVERLESS_MAX_UPLOAD_BYTES  # platform ceiling wins
        assert s.DB_POOL_SIZE + s.DB_MAX_OVERFLOW >= 20 and s.ML_MAX_OPTUNA_TRIALS <= 40 and not s.METRICS_ENABLED
    finally:
        monkeypatch.delenv("VERCEL")
        monkeypatch.delenv("MAX_UPLOAD_BYTES")
        importlib.reload(config_module)


# --- UTC timestamps -------------------------------------------------------------
def test_utc_datetime_type_round_trips_naive_utc(db_session):
    """Aware values of any zone are stored as the same instant and come back as
    naive UTC on every dialect (PostgreSQL returned aware values before)."""
    from app.models.system import AuditLog

    ist = timezone(timedelta(hours=5, minutes=30))
    row = AuditLog(action="api_call", resource="test", timestamp=datetime(2026, 1, 1, 15, 30, tzinfo=ist))
    db_session.add(row)
    db_session.commit()
    db_session.expire_all()
    stored = db_session.get(AuditLog, row.id).timestamp
    assert stored == datetime(2026, 1, 1, 10, 0)
    assert stored.tzinfo is None


# --- file storage -----------------------------------------------------------------
def test_database_storage_round_trip_and_usage(db_session, database_storage):
    locator = storage.save_file(db_session, storage.StorageCategory.REPORT, "a.csv", b"x,y\n1,2\n")
    db_session.commit()
    assert locator.startswith("db://")
    assert storage.read_file(db_session, locator) == b"x,y\n1,2\n"
    assert storage.usage_bytes(db_session, storage.StorageCategory.REPORT) == 8
    assert storage.usage_bytes(db_session, storage.StorageCategory.MODEL) == 0

    storage.delete_file(db_session, locator)
    db_session.commit()
    assert not storage.file_exists(db_session, locator)
    with pytest.raises(FileNotFoundError):
        storage.read_file(db_session, locator)


def test_filesystem_locators_stay_readable_after_switching_backend(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REPORT_STORAGE_DIR", str(tmp_path))
    locator = storage.save_file(db_session, storage.StorageCategory.REPORT, "old.csv", b"legacy")
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "database")
    assert storage.read_file(db_session, locator) == b"legacy"


def test_storage_quota_is_enforced(db_session, database_storage, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_QUOTA_BYTES", 10)
    storage.save_file(db_session, storage.StorageCategory.REPORT, "a", b"12345678")
    with pytest.raises(storage.StorageQuotaExceededException):
        storage.save_file(db_session, storage.StorageCategory.REPORT, "b", b"123")


def test_trained_model_is_served_from_database_storage(client, seeded_stock, database_storage, tmp_path, monkeypatch):
    """Train -> predict with no writable artifact directory at all."""
    monkeypatch.setattr(settings, "MODEL_ARTIFACT_DIR", str(tmp_path / "must-not-be-used"))
    trained = client.post("/api/v1/models/train", json={
        "symbol": seeded_stock, "n_optuna_trials": 2, "n_walk_forward_splits": 2,
    })
    assert trained.status_code == 200, trained.text

    from app.ml.registry import clear_artifact_cache

    clear_artifact_cache()  # force a real read back from the database
    predicted = client.post("/api/v1/predictions", json={"symbol": seeded_stock})
    assert predicted.status_code == 200, predicted.text
    assert predicted.json()["shap_contributions"]
    assert not (tmp_path / "must-not-be-used").exists()


def test_report_files_live_in_the_database_and_are_deleted_with_their_row(client, database_storage):
    from app.models.system import StoredFile

    created = client.post("/api/v1/reports/generate", json={"report_type": "prediction", "report_format": "csv"})
    assert created.status_code == 201, created.text
    report = created.json()

    download = client.get(f"/api/v1/reports/{report['id']}/download")
    assert download.status_code == 200 and len(download.content) == report["size_bytes"]

    assert client.delete(f"/api/v1/reports/{report['id']}").status_code == 200
    from app.core.database import get_db
    from app.main import app

    db = next(app.dependency_overrides[get_db]())
    assert db.query(StoredFile).count() == 0


def test_report_retention_keeps_only_the_newest(client, database_storage, monkeypatch):
    monkeypatch.setattr(settings, "REPORT_RETENTION_COUNT", 2)
    ids = [
        client.post("/api/v1/reports/generate", json={"report_type": "prediction", "report_format": "csv"}).json()["id"]
        for _ in range(3)
    ]
    remaining = {r["id"] for r in client.get("/api/v1/reports").json()}
    assert ids[0] not in remaining and set(ids[1:]) <= remaining


# --- public-deployment guards ------------------------------------------------------
def test_training_budget_is_enforced_before_any_work(client, seeded_stock, monkeypatch):
    monkeypatch.setattr(settings, "ML_MAX_OPTUNA_TRIALS", 5)
    response = client.post("/api/v1/models/train", json={"symbol": seeded_stock, "n_optuna_trials": 6})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "training_budget_exceeded"
    assert error["context"]["max_optuna_trials"] == 5


@pytest.mark.parametrize(("raw", "expected"), [
    ("203.0.113.57", "203.0.113.0"),
    ("2001:db8:85a3:1234::8a2e:370:7334", "2001:db8:85a3::"),
    ("testclient", "testclient"),
    (None, None),
])
def test_ip_anonymization(raw, expected):
    assert anonymize_ip(raw) == expected


def test_missing_optional_vector_store_is_a_clear_501(client, monkeypatch):
    import app.rag.vector_store as vector_store

    monkeypatch.setattr(vector_store, "chromadb_available", lambda: False)
    with pytest.raises(Exception) as excinfo:
        vector_store.new_vector_store("chromadb")
    assert getattr(excinfo.value, "status_code", None) == 501
