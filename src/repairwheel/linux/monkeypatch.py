from importlib import reload
from pathlib import Path
from typing import Dict, List


def init_policies_for_machine(machine: str) -> None:
    import platform

    orig_machine_fn = platform.machine
    try:
        platform.machine = lambda: machine
        import repairwheel._vendor.auditwheel.policy

        reload(repairwheel._vendor.auditwheel.policy)
    finally:
        platform.machine = orig_machine_fn


def patch_load_ld_paths(lib_paths: List[Path]) -> None:
    import repairwheel._vendor.auditwheel.lddtree

    def load_ld_paths(root: str = "/", prefix: str = "") -> Dict[str, List[str]]:
        return {
            "env": [str(lp) for lp in lib_paths],
            "conf": [],
            "interp": [],
        }

    repairwheel._vendor.auditwheel.lddtree.load_ld_paths = load_ld_paths


def apply_auditwheel_patches(target_machine: str, lib_paths: List[Path]) -> None:
    init_policies_for_machine(target_machine)
    patch_load_ld_paths(lib_paths)
