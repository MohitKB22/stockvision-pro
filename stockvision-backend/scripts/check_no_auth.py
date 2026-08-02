"""
Regression guard: assert the authentication subsystem has not returned.

Removing auth was a deliberate, wide-reaching change (see docs/CHANGELOG.md), and
the easiest way for it to creep back is one innocuous-looking import in a new
endpoint. This runs in CI.

Uses the AST rather than `grep`, because the source deliberately DISCUSSES the
removed subsystem in its CHANGE LOG docstrings — a naive text search matches those
comments and fails the build for describing history accurately. Parsing means we
check what the code *does*, not what it talks about.
"""
import ast
from pathlib import Path

FORBIDDEN_MODULES = {"jose", "passlib", "bcrypt", "app.core.security", "app.services.auth_service"}
FORBIDDEN_NAMES = {
    "OAuth2PasswordBearer", "OAuth2PasswordRequestForm",
    "get_current_user", "require_roles", "UserRole", "AuthService", "UserRepository",
}

APP_ROOT = Path(__file__).resolve().parent.parent / "app"


def module_is_forbidden(name: str | None) -> bool:
    if not name:
        return False
    return name in FORBIDDEN_MODULES or name.split(".")[0] in FORBIDDEN_MODULES


def scan(path: Path) -> list[str]:
    """Return human-readable findings for one file."""
    findings: list[str] = []
    tree = ast.parse(path.read_text(), filename=str(path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if module_is_forbidden(alias.name):
                    findings.append(f"{path}:{node.lineno}: imports `{alias.name}`")

        elif isinstance(node, ast.ImportFrom):
            if module_is_forbidden(node.module):
                findings.append(f"{path}:{node.lineno}: imports from `{node.module}`")
            for alias in node.names:
                if alias.name in FORBIDDEN_NAMES:
                    findings.append(f"{path}:{node.lineno}: imports `{alias.name}`")

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in FORBIDDEN_NAMES:
                findings.append(f"{path}:{node.lineno}: defines `{node.name}`")

        elif isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name in FORBIDDEN_NAMES:
                findings.append(f"{path}:{node.lineno}: calls `{name}`")

    return findings


def main() -> int:
    findings: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        findings.extend(scan(path))

    if findings:
        print("Authentication code found — it was removed in v2.0:\n")
        for finding in findings:
            print(f"  {finding}")
        return 1

    print(f"Clean: no authentication code across {sum(1 for _ in APP_ROOT.rglob('*.py'))} modules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
