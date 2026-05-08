from pathlib import Path
from typing import Dict, List


def patch_load_ld_paths(lib_paths: List[Path], use_sys_paths: bool) -> None:
    import repairwheel._vendor.auditwheel.lddtree

    if use_sys_paths:
        original_load_ld_paths = repairwheel._vendor.auditwheel.lddtree.load_ld_paths

        def load_ld_paths(root: str = "/", prefix: str = "") -> Dict[str, List[str]]:
            ldpaths = original_load_ld_paths(root, prefix)
            # Insert lib_paths at the beginning of the list
            ldpaths["env"][:0] = [str(lp) for lp in lib_paths]
            return ldpaths

    else:

        def load_ld_paths(root: str = "/", prefix: str = "") -> Dict[str, List[str]]:
            return {
                "env": [str(lp) for lp in lib_paths],
                "conf": [],
                "interp": [],
            }

    repairwheel._vendor.auditwheel.lddtree.load_ld_paths = load_ld_paths
