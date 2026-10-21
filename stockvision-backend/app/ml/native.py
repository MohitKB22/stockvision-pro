"""
OpenMP runtime for LightGBM on hosts that do not ship one.

LightGBM's Linux wheel links against the system ``libgomp.so.1`` (GCC's OpenMP
runtime) instead of bundling it, so ``import lightgbm`` fails with
``OSError: libgomp.so.1: cannot open shared object file`` wherever that system
library is missing — notably Vercel's Python runtime. XGBoost and scikit-learn
are unaffected: their wheels carry their own copy, renamed by auditwheel to
``libgomp-<hash>.so.1.0.0``.

``ensure_openmp_runtime()`` fixes this without system packages. If the dynamic
linker cannot find ``libgomp.so.1``, it copies one of those wheel-bundled copies
to a temporary directory, rewrites its ELF ``DT_SONAME`` back to
``libgomp.so.1`` and loads it. Once a library with that soname is in the
process, the dynamic linker uses it to satisfy LightGBM's dependency instead of
searching the filesystem. Nothing changes on hosts that already have the system
library: the first ``CDLL("libgomp.so.1")`` succeeds and the function returns.

Called from ``app/ml/__init__.py``, so it runs before anything under ``app.ml``
imports LightGBM (training) or unpickles a LightGBM model (prediction).
"""
from __future__ import annotations

import ctypes
import logging
import os
import struct
import sys
import tempfile
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

SONAME = b"libgomp.so.1"
_lock = threading.Lock()
_source: str | None = None
_handles: list[ctypes.CDLL] = []  # keeps the loaded library referenced

# ELF constants
_PT_LOAD, _PT_DYNAMIC = 1, 2
_DT_NULL, _DT_STRTAB, _DT_SONAME = 0, 5, 14


def ensure_openmp_runtime() -> str:
    """Makes ``libgomp.so.1`` resolvable. Idempotent and thread-safe.

    Returns where it came from: ``"system"``, the path of the wheel-bundled copy
    that was loaded, ``"missing"`` (nothing found; LightGBM will fail to import)
    or ``"not linux"``.
    """
    global _source
    if _source is not None:
        return _source
    with _lock:
        if _source is None:
            _source = _load()
        return _source


def _load() -> str:
    if not sys.platform.startswith("linux"):
        return "not linux"
    try:
        _handles.append(ctypes.CDLL(SONAME.decode()))
        return "system"
    except OSError:
        pass
    source = _bundled_libgomp()
    if source is None:
        logger.warning("libgomp.so.1 is missing and no wheel-bundled copy was found; "
                       "LightGBM will not load")
        return "missing"
    target = Path(tempfile.gettempdir()) / f"stockvision-openmp-{os.getpid()}" / SONAME.decode()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = bytearray(source.read_bytes())
    set_soname(data, SONAME)
    partial = target.with_suffix(".partial")
    partial.write_bytes(data)
    os.replace(partial, target)
    _handles.append(ctypes.CDLL(str(target)))
    logger.info("Loaded OpenMP runtime for LightGBM from %s", source)
    return str(source)


def _bundled_libgomp() -> Path | None:
    """A libgomp copy shipped inside an installed wheel (``<dist>.libs/``)."""
    for entry in sys.path:
        base = Path(entry or ".")
        if not base.is_dir():
            continue
        for candidate in sorted(base.glob("*.libs/libgomp*.so*")):
            if candidate.is_file():
                return candidate
    return None


def _soname_span(elf: bytes | bytearray) -> tuple[int, int]:
    """File offsets ``[start, end)`` of the ``DT_SONAME`` string of a 64-bit
    little-endian ELF shared object."""
    if elf[:4] != b"\x7fELF" or elf[4] != 2 or elf[5] != 1:
        raise ValueError("not a 64-bit little-endian ELF file")
    phoff = struct.unpack_from("<Q", elf, 0x20)[0]
    phentsize, phnum = struct.unpack_from("<HH", elf, 0x36)
    loads: list[tuple[int, int, int]] = []
    dynamic: tuple[int, int] | None = None
    for index in range(phnum):
        p_type, _flags, p_offset, p_vaddr, _paddr, p_filesz, _memsz, _align = struct.unpack_from(
            "<IIQQQQQQ", elf, phoff + index * phentsize)
        if p_type == _PT_LOAD:
            loads.append((p_vaddr, p_offset, p_filesz))
        elif p_type == _PT_DYNAMIC:
            dynamic = (p_offset, p_filesz)
    if dynamic is None:
        raise ValueError("ELF file has no dynamic section")

    tags: dict[int, int] = {}
    for offset in range(dynamic[0], dynamic[0] + dynamic[1], 16):
        tag, value = struct.unpack_from("<qQ", elf, offset)
        if tag == _DT_NULL:
            break
        tags.setdefault(tag, value)
    if _DT_STRTAB not in tags or _DT_SONAME not in tags:
        raise ValueError("ELF file has no DT_SONAME")

    strtab_vaddr = tags[_DT_STRTAB]
    strtab = next((offset + strtab_vaddr - vaddr for vaddr, offset, size in loads
                   if vaddr <= strtab_vaddr < vaddr + size), None)
    if strtab is None:
        raise ValueError("DT_STRTAB is outside every loadable segment")
    start = strtab + tags[_DT_SONAME]
    return start, elf.index(b"\0", start)


def read_soname(elf: bytes | bytearray) -> bytes:
    start, end = _soname_span(elf)
    return bytes(elf[start:end])


def set_soname(elf: bytearray, soname: bytes) -> None:
    """Rewrites an ELF shared object's ``DT_SONAME`` in place.

    The new name is written over the old string in the dynamic string table, so
    it must not be longer than the existing one (``libgomp.so.1`` is shorter than
    any ``libgomp-<hash>.so.1.0.0``). No offsets move, so the file stays valid.
    """
    start, end = _soname_span(elf)
    if len(soname) > end - start:
        raise ValueError(f"new soname {soname!r} is longer than {bytes(elf[start:end])!r}")
    elf[start:start + len(soname) + 1] = soname + b"\0"
