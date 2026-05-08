from pathlib import Path


def patch_load_ld_paths(lib_paths: list[Path], use_sys_paths: bool) -> None:
    import repairwheel._vendor.auditwheel.lddtree
    from repairwheel._vendor.auditwheel.libc import Libc

    if use_sys_paths:
        original_load_ld_paths = repairwheel._vendor.auditwheel.lddtree.load_ld_paths

        def load_ld_paths(libc: Libc | None = None, root: str = "/", prefix: str = "") -> dict[str, list[str]]:
            ldpaths = original_load_ld_paths(libc, root, prefix)
            # Insert lib_paths at the beginning of the list
            ldpaths["env"][:0] = [str(lp) for lp in lib_paths]
            return ldpaths

    else:

        def load_ld_paths(libc: Libc | None = None, root: str = "/", prefix: str = "") -> dict[str, list[str]]:
            return {
                "env": [str(lp) for lp in lib_paths],
                "conf": [],
                "interp": [],
            }

    repairwheel._vendor.auditwheel.lddtree.load_ld_paths = load_ld_paths
