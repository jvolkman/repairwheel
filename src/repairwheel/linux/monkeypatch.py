from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repairwheel._vendor.auditwheel.libc import Libc


def patch_load_ld_paths(lib_paths: list[Path], use_sys_paths: bool) -> None:
    import repairwheel._vendor.auditwheel.lddtree

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


_original_libc_detect = None
_original_wheel_policies_init = None


def patch_libc_detection(libc: Libc | None, musl_policy: str | None) -> None:
    """Monkeypatch vendored auditwheel to avoid host-based libc detection.

    Libc.detect() is always patched to avoid probing the host filesystem,
    keeping repairwheel as hermetic as possible:

    - When *libc* is known (MUSL or GLIBC), detect() returns that value.
    - When *libc* is None, detect() defaults to MUSL.  Glibc is always
      identifiable from ELF metadata (libc.so.6 in DT_NEEDED, versioned
      symbols), so if ELF inspection didn't identify glibc and we reach
      the detect() fallback, the wheel must target musl.

    When *libc* is MUSL and *musl_policy* is given, WheelPolicies.__init__
    is also patched to inject the musl_policy so the correct musllinux
    version is used without querying the host musl binary.

    Safe to call repeatedly (e.g. when repairing multiple wheels in one
    invocation): originals are saved on first call and restored before
    each new patch to prevent wrapper stacking.
    """
    global _original_libc_detect, _original_wheel_policies_init

    from repairwheel._vendor.auditwheel.libc import Libc as _Libc
    from repairwheel._vendor.auditwheel.architecture import Architecture
    from repairwheel._vendor.auditwheel.policy import WheelPolicies

    # Save originals on first call.
    if _original_libc_detect is None:
        _original_libc_detect = _Libc.detect
    if _original_wheel_policies_init is None:
        _original_wheel_policies_init = WheelPolicies.__init__

    # Always restore originals before patching so wrappers don't stack.
    WheelPolicies.__init__ = _original_wheel_policies_init  # type: ignore[method-assign]

    # Patch Libc.detect to return the known libc (or MUSL as the default
    # fallback) instead of probing the host.
    _libc_override = libc if libc is not None else _Libc.MUSL

    @staticmethod  # type: ignore[misc]
    def _detect() -> _Libc:
        return _libc_override

    _Libc.detect = _detect

    # Patch WheelPolicies.__init__ to inject musl_policy when not provided.
    if libc == _Libc.MUSL and musl_policy is not None:
        _musl_policy_override = musl_policy

        def _patched_init(
            self: WheelPolicies,
            *,
            libc: _Libc,
            arch: Architecture,
            musl_policy: str | None = None,
            wheel_fn: str | None = None,
        ) -> None:  # type: ignore[no-redef]
            if libc == _Libc.MUSL and musl_policy is None:
                musl_policy = _musl_policy_override
            _original_wheel_policies_init(self, libc=libc, arch=arch, musl_policy=musl_policy, wheel_fn=wheel_fn)

        WheelPolicies.__init__ = _patched_init  # type: ignore[method-assign]
