import argparse
import sys
from pathlib import Path
from typing import List, NoReturn
from typing import Set

from packaging.utils import parse_wheel_filename

from .linux.repair import repair as linux_repair
from .macos.repair import repair as macos_repair
from .windows.repair import repair as windows_repair


def fatal(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    sys.exit(1)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    parser.add_argument("wheel", type=Path)
    parser.add_argument("-o", "--output-dir", type=Path, required=True)
    parser.add_argument("-l", "--lib-dir", type=Path, action="append")

    return parser


def get_wheel_platforms(wheel: Path) -> Set[str]:
    result = set()
    _, _, _, tags = parse_wheel_filename(wheel.name)
    for tag in tags:
        if tag.platform == "any":
            result.add("any")
        elif tag.platform.startswith("linux") or tag.platform.startswith("manylinux"):
            result.add("linux")
        elif tag.platform.startswith("macos"):
            result.add("macos")
        elif tag.platform.startswith("win"):
            result.add("windows")

    return result


def main():
    parser = make_parser()
    args = parser.parse_args()

    wheel: Path = args.wheel.resolve()
    out: Path = args.output_dir.resolve()
    lib_path: List[Path] = [lp.resolve() for lp in args.lib_dir]

    if not wheel.is_file():
        fatal(f"File does not exist: {wheel}")

    platforms = get_wheel_platforms(wheel)
    if not platforms:
        fatal(f"No platforms detected in wheel name: {wheel.name}")

    if len(platforms) > 1:
        fatal(f"Multiple platforms detected in wheel name ({','.join(platforms)}); not sure what to do")

    platform = platforms.pop()
    if platform == "any":
        print("Nothing to do for any wheel")
        return

    fn = {
        "linux": linux_repair,
        "macos": macos_repair,
        "windows": windows_repair,
    }[platform]

    out.mkdir(parents=True, exist_ok=True)
    fn(wheel, out, lib_path)


if __name__ == "__main__":
    main()
