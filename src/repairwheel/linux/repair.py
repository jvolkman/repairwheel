from __future__ import annotations

import logging
import os
import re
import zlib
from pathlib import Path
from typing import TYPE_CHECKING

from packaging.utils import parse_wheel_filename

from . import monkeypatch
from . import patcher

if TYPE_CHECKING:
    from repairwheel._vendor.auditwheel.libc import Libc

log = logging.getLogger(__name__)


def _detect_libc_and_musl_policy(
    wheel_file: Path,
) -> tuple[Libc | None, str | None]:
    """Determine the target libc and musl policy from available signals.

    Detection order:
    1. AUDITWHEEL_PLAT environment variable
    2. Wheel filename platform tags
    3. None (let ELF inspection in get_wheel_elfdata determine libc)
    """
    # 1. Check AUDITWHEEL_PLAT environment variable
    auditwheel_plat = os.environ.get("AUDITWHEEL_PLAT", "")
    result = _parse_platform_for_libc(auditwheel_plat)
    if result is not None:
        return result

    # 2. Check wheel filename tags
    _, _, _, tags = parse_wheel_filename(wheel_file.name)
    for tag in tags:
        result = _parse_platform_for_libc(tag.platform)
        if result is not None:
            return result

    # 3. No explicit signal; let ELF inspection determine libc
    return None, None


def _parse_platform_for_libc(
    platform: str,
) -> tuple[Libc, str | None] | None:
    """Parse a platform string to extract libc type and musl policy.

    Returns (Libc, musl_policy) or None if the platform doesn't indicate a libc.
    """
    from repairwheel._vendor.auditwheel.libc import Libc

    m = re.match(r"(musllinux_\d+_\d+)", platform)
    if m:
        return Libc.MUSL, m.group(1)

    if platform.startswith("manylinux"):
        return Libc.GLIBC, None

    return None


def get_machine_from_wheel(wheel: Path) -> str:
    _, _, _, tags = parse_wheel_filename(wheel.name)
    tags = list(tags)
    first_tag = next(iter(tags))
    if len(tags) > 1:
        log.warning("Wheel %s has multiple tags; using first (%s)", wheel.name, first_tag)

    # platform is like 'linux_x86_64', 'manylinux_2_5_x86_64',
    # 'manylinux2014_aarch64', etc.  We can't simply split on '_'
    # because manylinux tags embed a version number.  Instead, try
    # each known architecture as a suffix.
    from repairwheel._vendor.auditwheel.architecture import Architecture

    plat = first_tag.platform
    for arch in Architecture:
        suffix = f"_{arch.value}"
        if plat.endswith(suffix):
            return arch.value

    # Fallback: assume the architecture is the part after the last '_'.
    return plat.rsplit("_", 1)[-1]


def repair(wheel_file: Path, output_dir: Path, lib_path: list[Path], use_sys_paths: bool, verbosity: int = 0) -> None:
    target_machine = get_machine_from_wheel(wheel_file)
    monkeypatch.patch_load_ld_paths(lib_path, use_sys_paths)

    from repairwheel._vendor.auditwheel.architecture import Architecture
    from repairwheel._vendor.auditwheel.error import InvalidLibcError, NonPlatformWheelError
    from repairwheel._vendor.auditwheel.repair import repair_wheel
    from repairwheel._vendor.auditwheel.wheel_abi import analyze_wheel_abi

    arch = Architecture(target_machine)
    libc, musl_policy = _detect_libc_and_musl_policy(wheel_file)
    log.info("Detected libc=%s, musl_policy=%s", libc, musl_policy)

    monkeypatch.patch_libc_detection(libc, musl_policy)

    try:
        winfo = analyze_wheel_abi(
            libc,
            arch,
            wheel_file,
            frozenset(),
            disable_isa_ext_check=False,
            allow_graft=True,
        )
    except NonPlatformWheelError as e:
        log.info(e.message)
        return
    except InvalidLibcError:
        log.warning(
            'Could not detect libc for wheel "%s". ' "Extensions may be statically linked. " "Skipping repair.",
            wheel_file.name,
        )
        return

    policies = winfo.policies
    if winfo.overall_policy == policies.linux:
        target_policy = policies.lowest
    else:
        target_policy = winfo.overall_policy

    abis = [target_policy.name, *target_policy.aliases]

    log.info(
        'Wheel "%s" is consistent with policy "%s". Repairing to "%s".',
        wheel_file.name,
        winfo.overall_policy.name,
        target_policy.name,
    )

    out_wheel = repair_wheel(
        winfo,
        wheel_file,
        abis=abis,
        lib_sdir=".libs",
        out_dir=output_dir,
        update_tags=True,
        patcher=patcher.RepairWheelElfPatcher(),
        strip=False,
        zip_compression_level=zlib.Z_DEFAULT_COMPRESSION,
    )

    if out_wheel is not None:
        log.info("Fixed-up wheel written to %s", out_wheel)
