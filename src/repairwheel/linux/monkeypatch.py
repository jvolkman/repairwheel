from pathlib import Path
from typing import Dict, List


def init_policies_for_machine(machine: str) -> None:
    from repairwheel._vendor.auditwheel import policy

    policies_for_machine = policy.WheelPolicies(
        libc=policy.Libc.GLIBC,  # TODO: support musl somehow
        arch=machine,
    )

    # Override the WheelPolicies class to always return our policies_for_machine
    policy.WheelPolicies = lambda: policies_for_machine


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


def apply_auditwheel_patches(target_machine: str, lib_paths: List[Path], use_sys_paths: bool) -> None:
    init_policies_for_machine(target_machine)
    patch_load_ld_paths(lib_paths, use_sys_paths)
