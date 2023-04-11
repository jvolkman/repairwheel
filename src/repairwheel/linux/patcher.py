from pathlib import Path
from typing import Tuple
from .elffile import ElfFile


class RepairWheelElfPatcher:
    def replace_needed(self, file_name: str, *old_new_pairs: Tuple[str, str]) -> None:
        replacements = {k.encode("utf-8"): v.encode("utf-8") for k, v in old_new_pairs}
        with open(file_name, "r+b") as f:
            ef = ElfFile(f)
            ef.rewrite(needed_replacements=replacements)

    def set_soname(self, file_name: str, new_so_name: str) -> None:
        with open(file_name, "r+b") as f:
            ef = ElfFile(f)
            ef.rewrite(new_soname=new_so_name.encode("utf-8"))

    def set_rpath(self, file_name: str, rpath: str) -> None:
        entries = rpath.split(":")
        for i, e in enumerate(entries):
            if e:
                entries[i] = Path(e).as_posix()
        rpath = ":".join(entries)
        with open(file_name, "r+b") as f:
            ef = ElfFile(f)
            ef.rewrite(new_rpath=rpath.encode("utf-8"))

    def get_rpath(self, file_name: str) -> str:
        with open(file_name, "r+b") as f:
            ef = ElfFile(f)
            val = ef.runpath or ef.rpath
            if val:
                return val.decode("utf-8")
        return ""
