import importlib
import os
from pathlib import Path
from typing import List


def _patch_tools():
    import repairwheel._vendor.delocate.tools as delocate_tools
    from . import machotools as patched_tools

    for fn_name in [
        "get_install_names",
        "get_install_id",
        "set_install_name",
        "set_install_id",
        "get_rpaths",
        "get_archs",
        "replace_signature",
        "validate_signature",
        "zip2dir",
        "dir2zip",
    ]:
        patched_fn = getattr(patched_tools, fn_name)
        setattr(delocate_tools, fn_name, patched_fn)

    # TODO: This is pretty brittle; there must be a better way.
    import repairwheel._vendor.delocate.delocating
    import repairwheel._vendor.delocate.libsana

    importlib.reload(repairwheel._vendor.delocate.delocating)
    importlib.reload(repairwheel._vendor.delocate.libsana)


def repair(wheel: Path, output_path: Path, lib_path: List[Path], verbosity: int = 0) -> Path:
    _patch_tools()
    from repairwheel._vendor.delocate.delocating import delocate_wheel

    # Set our path in DYLD_LIBRARY_PATH since that's where delocate looks.
    orig_env = {var: os.environ.get(var) for var in ["DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH"]}
    os.environ["DYLD_LIBRARY_PATH"] = ":".join(str(p) for p in lib_path)

    try:
        out_wheel = output_path / wheel.name
        delocate_wheel(
            in_wheel=wheel,
            out_wheel=out_wheel,
        )
    finally:
        # Restore os.environ
        for k, v in orig_env.items():
            if v is None:
                if k in os.environ:
                    del os.environ[k]
            else:
                os.environ[k] = v
