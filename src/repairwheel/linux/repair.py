import logging
import zlib
from pathlib import Path

from packaging.utils import parse_wheel_filename

from . import monkeypatch
from . import patcher

log = logging.getLogger(__name__)


def get_machine_from_wheel(wheel: Path) -> str:
    _, _, _, tags = parse_wheel_filename(wheel.name)
    tags = list(tags)
    first_tag = next(iter(tags))
    if len(tags) > 1:
        log.warning("Wheel %s has multiple tags; using first (%s)", wheel.name, first_tag)

    # platform is like 'linux_x86_64' or 'manylinux_aarch64'
    _, machine = first_tag.platform.split("_", 1)
    return machine


def repair(wheel_file: Path, output_dir: Path, lib_path: list[Path], use_sys_paths: bool, verbosity: int = 0) -> None:
    target_machine = get_machine_from_wheel(wheel_file)
    monkeypatch.patch_load_ld_paths(lib_path, use_sys_paths)

    from repairwheel._vendor.auditwheel.architecture import Architecture
    from repairwheel._vendor.auditwheel.error import NonPlatformWheelError
    from repairwheel._vendor.auditwheel.libc import Libc
    from repairwheel._vendor.auditwheel.repair import repair_wheel
    from repairwheel._vendor.auditwheel.wheel_abi import analyze_wheel_abi

    arch = Architecture(target_machine)

    try:
        winfo = analyze_wheel_abi(
            Libc.GLIBC,
            arch,
            wheel_file,
            frozenset(),
            disable_isa_ext_check=False,
            allow_graft=True,
        )
    except NonPlatformWheelError as e:
        log.info(e.message)
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
