"""
Diagnose why the backend will not start or will not answer.

Deliberately uses ONLY the standard library, so it runs even when the virtual
environment is broken or the requirements were never installed — the situations
where you most need a diagnosis.

    python3 scripts/doctor.py
"""
from __future__ import annotations

import importlib.util
import os
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

OK = "  ok   "
WARN = " warn  "
FAIL = " FAIL  "

problems: list[str] = []


def line(status: str, message: str) -> None:
    print(f"[{status}] {message}")


def header(title: str) -> None:
    print(f"\n--- {title} " + "-" * max(0, 58 - len(title)))


# --- 1. Interpreter -------------------------------------------------------------
header("Interpreter")
version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
line(OK if (3, 10) <= sys.version_info[:2] <= (3, 13) else FAIL, f"Python {version}")
if not ((3, 10) <= sys.version_info[:2] <= (3, 13)):
    problems.append(
        f"Python {version} is unsupported. faiss-cpu, xgboost, shap and scipy have no wheels "
        "for it. Rebuild the venv with python3.12."
    )

line(OK, f"executable: {sys.executable}")
in_venv = sys.prefix != sys.base_prefix
line(OK if in_venv else FAIL, f"virtualenv active: {in_venv}")
if not in_venv:
    problems.append(
        "You are not inside the project virtualenv. Run: source .venv/bin/activate "
        "(your prompt should then start with '(.venv)')."
    )

if os.environ.get("CONDA_DEFAULT_ENV"):
    line(
        WARN,
        f"conda env '{os.environ['CONDA_DEFAULT_ENV']}' is also active — "
        "always use 'python -m uvicorn', never bare 'uvicorn'",
    )


# --- 2. Working directory -------------------------------------------------------
header("Working directory")
cwd = Path.cwd()
line(OK, str(cwd))
has_app = (cwd / "app" / "main.py").is_file()
line(OK if has_app else FAIL, f"app/main.py present: {has_app}")
if not has_app:
    problems.append(
        "Wrong directory. cd into stockvision-backend (the folder that contains app/) "
        "before starting the API."
    )


# --- 3. Dependencies ------------------------------------------------------------
header("Dependencies")
required = [
    "fastapi", "uvicorn", "sqlalchemy", "pydantic", "pydantic_settings", "pandas",
    "numpy", "sklearn", "xgboost", "lightgbm", "shap", "faiss", "chromadb", "reportlab",
]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    line(FAIL, f"missing: {', '.join(missing)}")
    problems.append("Install dependencies: pip install -r requirements.txt")
else:
    line(OK, f"all {len(required)} key packages importable")


# --- 4. Database ----------------------------------------------------------------
header("Database")
db_path = cwd / "stockvision.db"
if db_path.is_file():
    size_mb = db_path.stat().st_size / 1_048_576
    line(OK, f"stockvision.db present ({size_mb:.1f} MB)")
    try:
        connection = sqlite3.connect(str(db_path))
        for table in ("stocks", "historical_prices", "portfolios", "news_articles"):
            try:
                count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                line(OK if count else WARN, f"{table}: {count:,} rows")
                if not count:
                    problems.append(f"Table {table} is empty — run: python scripts/seed_data.py")
            except sqlite3.Error:
                line(WARN, f"{table}: table not found")
        connection.close()
    except sqlite3.Error as exc:
        line(FAIL, f"could not read the database: {exc}")
else:
    line(FAIL, "stockvision.db not found")
    problems.append("Seed the database: python scripts/seed_data.py")


# --- 5. Port 8000 ---------------------------------------------------------------
header("Port 8000")


def probe(port: int) -> str:
    """Returns 'free', 'alive', or 'zombie'."""
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.settimeout(3)
    try:
        connection.connect(("127.0.0.1", port))
    except (ConnectionRefusedError, socket.timeout, OSError):
        return "free"
    try:
        connection.sendall(b"GET /health HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
        return "alive" if connection.recv(64) else "zombie"
    except (socket.timeout, OSError):
        return "zombie"
    finally:
        connection.close()


state = probe(8000)
if state == "free":
    line(OK, "nothing is listening — the port is available")
elif state == "alive":
    line(OK, "a server is listening and responding on 127.0.0.1:8000")
else:
    line(FAIL, "a process holds the port but never answers (a crashed --reload worker)")
    problems.append(
        "Kill the stale listener, then start the API again:\n"
        "        lsof -ti:8000 | xargs kill -9"
    )

try:
    listeners = subprocess.run(
        ["lsof", "-nP", "-iTCP:8000", "-sTCP:LISTEN"],
        capture_output=True, text=True, timeout=8,
    ).stdout.strip()
    if listeners:
        print("        " + listeners.replace("\n", "\n        "))
except (OSError, subprocess.SubprocessError):
    pass


# --- 6. Proxy settings ----------------------------------------------------------
header("Proxy environment")
proxy_vars = {
    name: os.environ[name]
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
    if os.environ.get(name)
}
no_proxy = os.environ.get("NO_PROXY", "") + os.environ.get("no_proxy", "")
if proxy_vars:
    line(WARN, f"proxy variables set: {', '.join(proxy_vars)}")
    if "localhost" not in no_proxy or "127.0.0.1" not in no_proxy:
        line(FAIL, "localhost is NOT in NO_PROXY — this makes localhost requests time out")
        problems.append(
            "A proxy is intercepting localhost. Either export "
            "NO_PROXY='localhost,127.0.0.1' or add both to the bypass list in "
            "System Settings -> Network -> Details -> Proxies. A browser timeout "
            "(rather than 'connection refused') on 127.0.0.1 is the classic symptom."
        )
    else:
        line(OK, "localhost is excluded from the proxy")
else:
    line(OK, "no proxy variables set")


# --- 7. Import the app ----------------------------------------------------------
header("Application import")
if has_app and not missing:
    sys.path.insert(0, str(cwd))
    try:
        import app.main  # noqa: F401

        line(OK, "app.main imported cleanly — the API itself is fine")
    except Exception as exc:  # noqa: BLE001 — reporting any failure is the point
        line(FAIL, f"{type(exc).__name__}: {exc}")
        problems.append(f"The app fails to import: {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
else:
    line(WARN, "skipped (fix the checks above first)")


# --- Verdict --------------------------------------------------------------------
print()
if problems:
    print("=" * 66)
    print(f"{len(problems)} problem(s) found:\n")
    for index, problem in enumerate(problems, start=1):
        print(f"  {index}. {problem}\n")
    print("=" * 66)
    sys.exit(1)

print("=" * 66)
print("No problems found. Start the API with:")
print("    python -m uvicorn app.main:app --reload")
print("=" * 66)
