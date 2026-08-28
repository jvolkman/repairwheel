from pathlib import Path

from repairwheel._vendor.auditwheel.patcher import ElfPatcher, ElfUpdateInfo
from .elffile import ElfFile


class RepairWheelElfPatcher(ElfPatcher):
    def __init__(self, platform: str = "") -> None:
        super().__init__(platform)

    def _update_for(self, file_name: Path | str) -> ElfUpdateInfo:
        return self._updates[Path(file_name).resolve(strict=True)]

    def get_rpath(self, file_name: Path | str) -> str:
        return super().get_rpath(Path(file_name))

    def get_rpath_direct(self, file_name: Path | str) -> str:
        with open(file_name, "r+b") as f:
            ef = ElfFile(f)
            val = ef.runpath or ef.rpath
            if val:
                return val.decode("utf-8")
        return ""

    def apply_updates(self) -> None:
        elf_files = list(self._updates.keys())
        for filepath in elf_files:
            update_info = self._updates.pop(filepath)

            new_soname = update_info.soname.encode("utf-8") if update_info.soname is not None else None

            replacements = (
                {k.encode("utf-8"): v.encode("utf-8") for k, v in update_info.replace_needed}
                if update_info.replace_needed
                else None
            )

            removals = {s.encode("utf-8") for s in update_info.remove_needed} if update_info.remove_needed else None

            new_rpath = None
            if update_info.rpath is not None:
                entries = update_info.rpath.split(":")
                for i, e in enumerate(entries):
                    if e:
                        entries[i] = Path(e).as_posix()
                new_rpath = ":".join(entries).encode("utf-8")
            elif update_info.clear_rpath:
                new_rpath = b""

            if new_soname is not None or new_rpath is not None or replacements or removals:
                with open(filepath, "r+b") as f:
                    ef = ElfFile(f)
                    ef.rewrite(
                        new_soname=new_soname,
                        new_rpath=new_rpath,
                        needed_replacements=replacements,
                        needed_removals=removals,
                    )
        assert len(self._updates) == 0
