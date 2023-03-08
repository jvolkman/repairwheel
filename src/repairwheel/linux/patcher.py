import shutil
from typing import Tuple
from .elffile import ElfFile


patch_num = 0


def do_patch(file_name, **params):
    global patch_num
    patch_num += 1
    with open(file_name, "r+b") as f:
        with open(f"/tmp/elfpatch.{patch_num}.in", "wb") as f2:
            shutil.copyfileobj(f, f2)
        with open(f"/tmp/elfpatch.{patch_num}.args", "w") as f2:
            f2.write(str(params))

        f.seek(0)
        ef = ElfFile(f)
        ef.rewrite(**params)

        f.seek(0)
        with open(f"/tmp/elfpatch.{patch_num}.out", "wb") as f2:
            shutil.copyfileobj(f, f2)


class RepairWheelElfPatcher:
    def replace_needed(self, file_name: str, *old_new_pairs: Tuple[str, str]) -> None:
        replacements = {k.encode("utf-8"): v.encode("utf-8") for k, v in old_new_pairs}
        # with open(file_name, "r+b") as f:
        #     ef = ElfFile(f)
        #     ef.rewrite(needed_replacements=replacements)
        do_patch(file_name, needed_replacements=replacements)

    def set_soname(self, file_name: str, new_so_name: str) -> None:
        # with open(file_name, "r+b") as f:
        #     ef = ElfFile(f)
        #     ef.rewrite(new_soname=new_so_name.encode("utf-8"))
        do_patch(file_name, new_soname=new_so_name.encode("utf-8"))

    def set_rpath(self, file_name: str, rpath: str) -> None:
        # with open(file_name, "r+b") as f:
        #     ef = ElfFile(f)
        #     ef.rewrite(new_rpath=rpath.encode("utf-8"))
        do_patch(file_name, new_rpath=rpath.encode("utf-8"))

    def get_rpath(self, file_name: str) -> str:
        with open(file_name, "r+b") as f:
            ef = ElfFile(f)
            val = ef.runpath or ef.rpath
            if val:
                return val.decode("utf-8")
        return ""
