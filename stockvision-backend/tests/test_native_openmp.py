"""
The OpenMP fallback that lets LightGBM load on hosts without a system
libgomp.so.1 (Vercel's Python runtime). See app/ml/native.py.

CI additionally runs model training with the system library hidden, which is
the end-to-end version of these checks.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app.ml.native import SONAME, _bundled_libgomp, read_soname, set_soname

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="ELF/Linux only")

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def bundled() -> Path:
    path = _bundled_libgomp()
    assert path is not None, "xgboost/scikit-learn wheels ship a libgomp copy; none was found"
    return path


def test_bundled_copy_has_a_renamed_soname(bundled):
    soname = read_soname(bundled.read_bytes())
    assert soname.startswith(b"libgomp-") and soname != SONAME


def test_set_soname_rewrites_only_the_soname_string(bundled):
    original = bundled.read_bytes()
    patched = bytearray(original)
    set_soname(patched, SONAME)

    assert read_soname(patched) == SONAME
    assert len(patched) == len(original)
    changed = [i for i, (a, b) in enumerate(zip(original, patched)) if a != b]
    assert changed and max(changed) - min(changed) < len(read_soname(original))


def test_set_soname_refuses_a_longer_name(bundled):
    data = bytearray(bundled.read_bytes())
    with pytest.raises(ValueError, match="longer"):
        set_soname(data, b"libgomp-" + b"x" * 200 + b".so.1")


def test_set_soname_rejects_non_elf():
    with pytest.raises(ValueError, match="ELF"):
        set_soname(bytearray(b"not an elf file" * 10), SONAME)


def test_fallback_loads_a_patched_copy_when_the_system_library_is_missing(tmp_path):
    """Simulates the missing system library by making the bare-name CDLL call
    fail, in a fresh interpreter so the process-wide state starts clean."""
    script = textwrap.dedent(f"""
        import ctypes, os, sys, tempfile
        real_init = ctypes.CDLL.__init__
        def no_system_gomp(self, name, *args, **kwargs):
            if name == "libgomp.so.1":
                raise OSError("libgomp.so.1: cannot open shared object file")
            real_init(self, name, *args, **kwargs)
        ctypes.CDLL.__init__ = no_system_gomp
        tempfile.tempdir = {str(tmp_path)!r}

        from app.ml.native import ensure_openmp_runtime, read_soname
        source = ensure_openmp_runtime()
        assert source.endswith(".so.1.0.0") and ".libs" in source, source
        assert ensure_openmp_runtime() == source  # idempotent
        patched = os.path.join({str(tmp_path)!r}, f"stockvision-openmp-{{os.getpid()}}", "libgomp.so.1")
        assert read_soname(open(patched, "rb").read()) == b"libgomp.so.1"
        maps = open("/proc/self/maps").read()
        assert patched in maps, "patched libgomp was not mapped into the process"
        print("ok")
    """)
    result = subprocess.run([sys.executable, "-c", script], cwd=BACKEND, capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip().endswith("ok")


def test_system_library_is_used_when_present():
    """On a normal host nothing is copied or patched."""
    import ctypes

    try:
        ctypes.CDLL("libgomp.so.1")
    except OSError:
        pytest.skip("this host has no system libgomp.so.1")
    result = subprocess.run(
        [sys.executable, "-c", "from app.ml.native import ensure_openmp_runtime as e; print(e())"],
        cwd=BACKEND, capture_output=True, text=True, timeout=60)
    assert result.stdout.strip() == "system", result.stderr[-2000:]
