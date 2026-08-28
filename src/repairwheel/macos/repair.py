import fnmatch
import importlib
import os
from collections.abc import Callable
from pathlib import Path


def _patch_tools():
    import repairwheel._vendor.delocate.tools as delocate_tools
    from . import machotools as patched_tools

    for fn_name in [
        "_get_install_names",
        "_get_install_ids",
        "_get_rpaths",
        "set_install_name",
        "set_install_id",
        "get_archs",
        "replace_signature",
        "validate_signature",
    ]:
        patched_fn = getattr(patched_tools, fn_name)
        setattr(delocate_tools, fn_name, patched_fn)

    # TODO: This is pretty brittle; there must be a better way.
    import repairwheel._vendor.delocate.delocating
    import repairwheel._vendor.delocate.libsana

    importlib.reload(repairwheel._vendor.delocate.delocating)
    importlib.reload(repairwheel._vendor.delocate.libsana)


def make_copy_filt_func(exclude: list[str] | None = None) -> Callable[[str], bool]:
    from repairwheel._vendor.delocate.libsana import filter_system_libs

    exclude_patterns = list(exclude or [])

    def copy_filt_func(libname: str) -> bool:
        if not filter_system_libs(libname):
            return False
        lib_basename = os.path.basename(libname)
        return not any(fnmatch.fnmatch(lib_basename, pat) or fnmatch.fnmatch(libname, pat) for pat in exclude_patterns)

    return copy_filt_func


def repair(
    wheel: Path,
    output_path: Path,
    lib_path: list[Path],
    use_sys_paths: bool,
    exclude: list[str] | None = None,
    verbosity: int = 0,
) -> None:
    _patch_tools()
    from repairwheel._vendor.delocate.delocating import delocate_wheel

    copy_filt_func = make_copy_filt_func(exclude)

    # Set our path in DYLD_LIBRARY_PATH since that's where delocate looks.
    orig_env = {var: os.environ.get(var) for var in ["DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH"]}
    lib_path_str = os.pathsep.join(str(p) for p in lib_path)
    if use_sys_paths:
        if lib_path_str:
            if orig_env["DYLD_LIBRARY_PATH"]:
                new_dyld_lib_path = lib_path_str + os.pathsep + orig_env["DYLD_LIBRARY_PATH"]
            else:
                new_dyld_lib_path = lib_path_str
            os.environ["DYLD_LIBRARY_PATH"] = new_dyld_lib_path
    else:
        os.environ["DYLD_LIBRARY_PATH"] = lib_path_str

    try:
        out_wheel = output_path / wheel.name
        delocate_wheel(
            in_wheel=wheel,
            out_wheel=out_wheel,
            copy_filt_func=copy_filt_func,
        )
    finally:
        # Restore os.environ
        for k, v in orig_env.items():
            if v is None:
                if k in os.environ:
                    del os.environ[k]
            else:
                os.environ[k] = v
