import argparse
import logging
from pathlib import Path
from typing import List

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


def repair(wheel_file: Path, output_dir: Path, lib_path: List[Path], use_sys_paths: bool, verbosity: int = 0) -> None:
    target_machine = get_machine_from_wheel(wheel_file)
    monkeypatch.apply_auditwheel_patches(target_machine, lib_path, use_sys_paths)

    from repairwheel._vendor.auditwheel.policy import WheelPolicies
    from repairwheel._vendor.auditwheel.wheel_abi import analyze_wheel_abi, NonPlatformWheel

    try:
        winfo = analyze_wheel_abi(WheelPolicies(), str(wheel_file), frozenset())
    except NonPlatformWheel:
        log.info(NonPlatformWheel.LOG_MESSAGE)
        return

    show_parser = argparse.ArgumentParser()
    show_sub_parsers = show_parser.add_subparsers(metavar="command", dest="cmd")

    repair_parser = argparse.ArgumentParser()
    repair_sub_parsers = repair_parser.add_subparsers(metavar="command", dest="cmd")

    from repairwheel._vendor.auditwheel import main_repair, main_show

    main_repair.Patchelf = patcher.RepairWheelElfPatcher

    main_show.configure_parser(show_sub_parsers)
    main_repair.configure_parser(repair_sub_parsers)

    show_args = show_parser.parse_args(["show", str(wheel_file)])
    show_args.verbose = verbosity
    show_args.func(show_args, show_parser)

    repair_args = repair_parser.parse_args(
        [
            "repair",
            str(wheel_file),
            "--only-plat",
            "--plat",
            winfo.sym_tag,
            "--wheel-dir",
            str(output_dir),
        ]
    )
    repair_args.verbose = verbosity
    repair_args.func(repair_args, repair_parser)
