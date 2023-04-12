from contextlib import contextmanager
import copy
from dataclasses import dataclass
import io
from typing import BinaryIO, Dict, Generator, Optional, Set, Tuple
from typing import List
from typing import Union

from macholib.ptypes import Structure
from macholib.ptypes import p_int32
from macholib.ptypes import p_int64
from macholib.ptypes import p_uint8
from macholib.ptypes import p_uint16
from macholib.ptypes import p_uint32
from macholib.ptypes import p_uint64
from macholib.ptypes import sizeof

from ..fileutil import fzero
from ..fileutil import round_to_multiple

try:
    from functools import cached_property
except ImportError:
    from ..compat import cached_property

# http://blog.k3170makan.com/2018/09/introduction-to-elf-format-part-ii.html
# https://www.cs.cmu.edu/afs/cs/academic/class/15213-f00/docs/elf.pdf


Elf32_Half = p_uint16
Elf32_Word = p_uint32
Elf32_Sword = p_int32
Elf32_Addr = p_uint32
Elf32_Off = p_uint32

Elf64_Half = p_uint16
Elf64_Word = p_uint32
Elf64_Sword = p_int32
Elf64_Xword = p_uint64
Elf64_Sxword = p_int64
Elf64_Addr = p_uint64
Elf64_Off = p_uint64

# The four ELF magic number parts
ELF_MAGIC = (0x7F, ord("E"), ord("L"), ord("F"))

ELFCLASS32 = 1
ELFCLASS64 = 2

ELFDATA2LSB = 1  # 2's complement, little endian
ELFDATA2MSB = 2  # 2's complement, big endian

ET_DYN = 3  # Shared object file

PT_NULL = 0  # Program header table entry unused
PT_LOAD = 1  # Loadable program segment
PT_DYNAMIC = 2  # Dynamic linking information
PT_INTERP = 3  # Program interpreter
PT_NOTE = 4  # Auxiliary information
PT_SHLIB = 5  # Reserved
PT_PHDR = 6  # Entry for header table itself
PT_TLS = 7  # Thread-local storage segment
PT_NUM = 8  # Number of defined types
PT_GNU_RELRO = 0x6474E552

PF_R = 0x4
PF_W = 0x2
PF_X = 0x1

SHT_STRTAB = 3
SHT_DYNAMIC = 6

DT_NULL = 0
DT_NEEDED = 1
DT_STRTAB = 5
DT_STRSZ = 10
DT_SONAME = 14
DT_RPATH = 15
DT_RUNPATH = 29
DT_VERNEED = 0x6FFFFFFE
DT_VERNEEDNUM = 0x6FFFFFFF


class ElfIdent(Structure):
    _fields_ = [
        ("ei_mag0", p_uint8),
        ("ei_mag1", p_uint8),
        ("ei_mag2", p_uint8),
        ("ei_mag3", p_uint8),
        ("ei_class", p_uint8),
        ("ei_data", p_uint8),
        ("ei_version", p_uint8),
        ("ei_osabi", p_uint8),
        ("ei_abiversion", p_uint8),
        ("ei_pad1", p_uint8),
        ("ei_pad2", p_uint8),
        ("ei_pad3", p_uint8),
        ("ei_pad4", p_uint8),
        ("ei_pad5", p_uint8),
        ("ei_pad6", p_uint8),
        ("ei_pad7", p_uint8),
    ]


_Elf32_Ehdr_fields = [
    *ElfIdent._fields_,
    ("e_type", Elf32_Half),
    ("e_machine", Elf32_Half),
    ("e_version", Elf32_Word),
    ("e_entry", Elf32_Addr),
    ("e_phoff", Elf32_Off),
    ("e_shoff", Elf32_Off),
    ("e_flags", Elf32_Word),
    ("e_ehsize", Elf32_Half),
    ("e_phentsize", Elf32_Half),
    ("e_phnum", Elf32_Half),
    ("e_shentsize", Elf32_Half),
    ("e_shnum", Elf32_Half),
    ("e_shstrndx", Elf32_Half),
]


class Elf32_Ehdr_BE(Structure):
    _endian_ = ">"
    _fields_ = _Elf32_Ehdr_fields


class Elf32_Ehdr_LE(Structure):
    _endian_ = "<"
    _fields_ = _Elf32_Ehdr_fields


_Elf64_Ehdr_fields = [
    *ElfIdent._fields_,
    ("e_type", Elf64_Half),
    ("e_machine", Elf64_Half),
    ("e_version", Elf64_Word),
    ("e_entry", Elf64_Addr),
    ("e_phoff", Elf64_Off),
    ("e_shoff", Elf64_Off),
    ("e_flags", Elf64_Word),
    ("e_ehsize", Elf64_Half),
    ("e_phentsize", Elf64_Half),
    ("e_phnum", Elf64_Half),
    ("e_shentsize", Elf64_Half),
    ("e_shnum", Elf64_Half),
    ("e_shstrndx", Elf64_Half),
]


class Elf64_Ehdr_BE(Structure):
    _endian_ = ">"
    _fields_ = _Elf64_Ehdr_fields


class Elf64_Ehdr_LE(Structure):
    _endian_ = "<"
    _fields_ = _Elf64_Ehdr_fields


_Elf32_Phdr_fields = [
    ("p_type", Elf32_Word),
    ("p_offset", Elf32_Off),
    ("p_vaddr", Elf32_Addr),
    ("p_paddr", Elf32_Addr),
    ("p_filesz", Elf32_Word),
    ("p_memsz", Elf32_Word),
    ("p_flags", Elf32_Word),
    ("p_align", Elf32_Word),
]


class Elf32_Phdr_BE(Structure):
    _endian_ = ">"
    _fields_ = _Elf32_Phdr_fields


class Elf32_Phdr_LE(Structure):
    _endian_ = "<"
    _fields_ = _Elf32_Phdr_fields


_Elf64_Phdr_fields = [
    ("p_type", Elf64_Word),
    ("p_flags", Elf64_Word),
    ("p_offset", Elf64_Off),
    ("p_vaddr", Elf64_Addr),
    ("p_paddr", Elf64_Addr),
    ("p_filesz", Elf64_Xword),
    ("p_memsz", Elf64_Xword),
    ("p_align", Elf64_Xword),
]


class Elf64_Phdr_BE(Structure):
    _endian_ = ">"
    _fields_ = _Elf64_Phdr_fields


class Elf64_Phdr_LE(Structure):
    _endian_ = "<"
    _fields_ = _Elf64_Phdr_fields


_Elf32_Shdr_fields = [
    ("sh_name", Elf32_Word),
    ("sh_type", Elf32_Word),
    ("sh_flags", Elf32_Word),
    ("sh_addr", Elf32_Addr),
    ("sh_offset", Elf32_Off),
    ("sh_size", Elf32_Word),
    ("sh_link", Elf32_Word),
    ("sh_info", Elf32_Word),
    ("sh_addralign", Elf32_Word),
    ("sh_entsize", Elf32_Word),
]


class Elf32_Shdr_BE(Structure):
    _endian_ = ">"
    _fields_ = _Elf32_Shdr_fields


class Elf32_Shdr_LE(Structure):
    _endian_ = "<"
    _fields_ = _Elf32_Shdr_fields


_Elf64_Shdr_fields = [
    ("sh_name", Elf64_Word),
    ("sh_type", Elf64_Word),
    ("sh_flags", Elf64_Xword),
    ("sh_addr", Elf64_Addr),
    ("sh_offset", Elf64_Off),
    ("sh_size", Elf64_Xword),
    ("sh_link", Elf64_Word),
    ("sh_info", Elf64_Word),
    ("sh_addralign", Elf64_Xword),
    ("sh_entsize", Elf64_Xword),
]


class Elf64_Shdr_BE(Structure):
    _endian_ = ">"
    _fields_ = _Elf64_Shdr_fields


class Elf64_Shdr_LE(Structure):
    _endian_ = "<"
    _fields_ = _Elf64_Shdr_fields


_Elf32_Dyn_fields = [
    ("d_tag", Elf32_Sword),
    ("d_ptr_or_val", Elf32_Addr),  # union of d_ptr and d_val
]


class Elf32_Dyn_BE(Structure):
    _endian_ = ">"
    _fields_ = _Elf32_Dyn_fields


class Elf32_Dyn_LE(Structure):
    _endian_ = "<"
    _fields_ = _Elf32_Dyn_fields


_Elf64_Dyn_fields = [
    ("d_tag", Elf64_Sxword),
    ("d_ptr_or_val", Elf64_Addr),  # union of d_ptr and d_val
]


class Elf64_Dyn_BE(Structure):
    _endian_ = ">"
    _fields_ = _Elf64_Dyn_fields


class Elf64_Dyn_LE(Structure):
    _endian_ = "<"
    _fields_ = _Elf64_Dyn_fields


_Elf32_Sym_fields = [
    ("st_name", Elf32_Word),
    ("st_value", Elf32_Addr),
    ("st_size", Elf32_Word),
    ("st_info", p_uint8),
    ("st_other", p_uint8),
    ("st_shndx", Elf32_Half),
]


class Elf32_Sym_BE(Structure):
    _endian_ = ">"
    _fields_ = _Elf32_Sym_fields


class Elf32_Sym_LE(Structure):
    _endian_ = "<"
    _fields_ = _Elf32_Sym_fields


_Elf64_Sym_fields = [
    ("st_name", Elf64_Word),
    ("st_info", p_uint8),
    ("st_other", p_uint8),
    ("st_shndx", Elf64_Half),
    ("st_value", Elf64_Addr),
    ("st_size", Elf64_Xword),
]


class Elf64_Sym_BE(Structure):
    _endian_ = ">"
    _fields_ = _Elf64_Sym_fields


class Elf64_Sym_LE(Structure):
    _endian_ = "<"
    _fields_ = _Elf64_Sym_fields


_Elf32_Verneed_fields = [
    ("vn_version", Elf32_Half),
    ("vn_cnt", Elf32_Half),
    ("vn_file", Elf32_Word),
    ("vn_aux", Elf32_Word),
    ("vn_next", Elf32_Word),
]


class Elf32_Verneed_BE(Structure):
    _endian_ = ">"
    _fields_ = _Elf32_Verneed_fields


class Elf32_Verneed_LE(Structure):
    _endian_ = "<"
    _fields_ = _Elf32_Verneed_fields


_Elf64_Verneed_fields = [
    ("vn_version", Elf64_Half),
    ("vn_cnt", Elf64_Half),
    ("vn_file", Elf64_Word),
    ("vn_aux", Elf64_Word),
    ("vn_next", Elf64_Word),
]


class Elf64_Verneed_BE(Structure):
    _endian_ = ">"
    _fields_ = _Elf64_Verneed_fields


class Elf64_Verneed_LE(Structure):
    _endian_ = "<"
    _fields_ = _Elf64_Verneed_fields


_Elf32_Vernaux_fields = [
    ("vna_hash", Elf32_Word),
    ("vna_flags", Elf32_Half),
    ("vna_other", Elf32_Half),
    ("vna_name", Elf32_Word),
    ("vna_next", Elf32_Word),
]


class Elf32_Vernaux_BE(Structure):
    _endian_ = ">"
    _fields_ = _Elf32_Vernaux_fields


class Elf32_Vernaux_LE(Structure):
    _endian_ = "<"
    _fields_ = _Elf32_Vernaux_fields


_Elf64_Vernaux_fields = [
    ("vna_hash", Elf64_Word),
    ("vna_flags", Elf64_Half),
    ("vna_other", Elf64_Half),
    ("vna_name", Elf64_Word),
    ("vna_next", Elf64_Word),
]


class Elf64_Vernaux_BE(Structure):
    _endian_ = ">"
    _fields_ = _Elf64_Vernaux_fields


class Elf64_Vernaux_LE(Structure):
    _endian_ = "<"
    _fields_ = _Elf64_Vernaux_fields


Elf_Ehdr = Union[Elf32_Ehdr_BE, Elf32_Ehdr_LE, Elf64_Ehdr_BE, Elf64_Ehdr_LE]
Elf_Phdr = Union[Elf32_Phdr_BE, Elf32_Phdr_LE, Elf64_Phdr_BE, Elf64_Phdr_LE]
Elf_Shdr = Union[Elf32_Shdr_BE, Elf32_Shdr_LE, Elf64_Shdr_BE, Elf64_Shdr_LE]
Elf_Dyn = Union[Elf32_Dyn_BE, Elf32_Dyn_LE, Elf64_Dyn_BE, Elf64_Dyn_LE]
Elf_Sym = Union[Elf32_Sym_BE, Elf32_Sym_LE, Elf64_Sym_BE, Elf64_Sym_LE]
Elf_Verneed = Union[Elf32_Verneed_BE, Elf32_Verneed_LE, Elf64_Verneed_BE, Elf64_Verneed_LE]
Elf_Vernaux = Union[Elf32_Vernaux_BE, Elf32_Vernaux_LE, Elf64_Vernaux_BE, Elf64_Vernaux_LE]


@dataclass
class ElfClass:
    alignment: int
    Ehdr: Elf_Ehdr
    Phdr: Elf_Phdr
    Shdr: Elf_Shdr
    Dyn: Elf_Dyn
    Sym: Elf_Sym
    Verneed: Elf_Verneed
    Vernaux: Elf_Vernaux


ELF32_CLASS_BE = ElfClass(
    alignment=sizeof(Elf32_Off),
    Ehdr=Elf32_Ehdr_BE,
    Phdr=Elf32_Phdr_BE,
    Shdr=Elf32_Shdr_BE,
    Dyn=Elf32_Dyn_BE,
    Sym=Elf32_Sym_BE,
    Verneed=Elf32_Verneed_BE,
    Vernaux=Elf32_Vernaux_BE,
)

ELF32_CLASS_LE = ElfClass(
    alignment=sizeof(Elf32_Off),
    Ehdr=Elf32_Ehdr_LE,
    Phdr=Elf32_Phdr_LE,
    Shdr=Elf32_Shdr_LE,
    Dyn=Elf32_Dyn_LE,
    Sym=Elf32_Sym_LE,
    Verneed=Elf32_Verneed_LE,
    Vernaux=Elf32_Vernaux_LE,
)

ELF64_CLASS_BE = ElfClass(
    alignment=sizeof(Elf64_Off),
    Ehdr=Elf64_Ehdr_BE,
    Phdr=Elf64_Phdr_BE,
    Shdr=Elf64_Shdr_BE,
    Dyn=Elf64_Dyn_BE,
    Sym=Elf64_Sym_BE,
    Verneed=Elf64_Verneed_BE,
    Vernaux=Elf64_Vernaux_BE,
)

ELF64_CLASS_LE = ElfClass(
    alignment=sizeof(Elf64_Off),
    Ehdr=Elf64_Ehdr_LE,
    Phdr=Elf64_Phdr_LE,
    Shdr=Elf64_Shdr_LE,
    Dyn=Elf64_Dyn_LE,
    Sym=Elf64_Sym_LE,
    Verneed=Elf64_Verneed_LE,
    Vernaux=Elf64_Vernaux_LE,
)


@dataclass
class VerneedEntry:
    verneed: Elf_Verneed
    vernaux: List[Elf_Vernaux]
    verneed_name: bytes
    vernaux_names: List[bytes]


@dataclass
class SectionInfo:
    file_offset: int
    vm_offset: int
    length: int
    count: Optional[int] = None


class PositionTracker:
    def __init__(self, file_offset: int, vm_offset: int):
        self.file_start = file_offset
        self.vm_start = vm_offset
        self.file_offset = file_offset
        self.max_file_offset = file_offset
        self.vm_offset = vm_offset
        self.max_vm_offset = vm_offset

    def add(self, count: int) -> None:
        self.file_offset += count
        self.max_file_offset = max(self.file_offset, self.max_file_offset)
        self.vm_offset += count
        self.max_vm_offset = max(self.vm_offset, self.max_vm_offset)

    def round(self, align: int) -> None:
        if not align:
            # An alignment of 0 or 1 mean no alignment.
            # But passing 0 to round_to_multiple will cause ZeroDivisionError.
            align = 1
        self.file_offset = round_to_multiple(self.file_offset, align)
        self.max_file_offset = max(self.file_offset, self.max_file_offset)
        self.vm_offset = round_to_multiple(self.vm_offset, align)
        self.max_vm_offset = max(self.vm_offset, self.max_vm_offset)

    def back_to_start(self) -> None:
        self.file_offset = self.file_start
        self.vm_offset = self.vm_start

    @property
    def buf_offset(self) -> int:
        return self.file_offset - self.file_start

    @property
    def file_size(self) -> int:
        return self.max_file_offset - self.file_start

    @property
    def vm_size(self) -> int:
        return self.max_vm_offset - self.vm_start


@dataclass
class Dynstr:
    strtab: bytes
    soname_pos: int
    rpath_pos: int
    needed_pos: Dict[bytes, int]
    vernaux_pos: Dict[bytes, int]


class ElfFile:
    def __init__(self, fh: BinaryIO):
        self._fh = fh

        ident = self.ident
        self.elf_class = ident.ei_class

        if ident.ei_class not in (ELFCLASS32, ELFCLASS64):
            raise ValueError(f"Unknown ei_class value: {ident.ei_class}")

        if ident.ei_data not in (ELFDATA2MSB, ELFDATA2LSB):
            raise ValueError(f"Unknown ei_data value: {ident.ei_data}")

        self._class = {
            (ELFCLASS32, ELFDATA2MSB): ELF32_CLASS_BE,
            (ELFCLASS32, ELFDATA2LSB): ELF32_CLASS_LE,
            (ELFCLASS64, ELFDATA2MSB): ELF64_CLASS_BE,
            (ELFCLASS64, ELFDATA2LSB): ELF64_CLASS_LE,
        }[(ident.ei_class, ident.ei_data)]

    @contextmanager
    def _peek(self) -> Generator[BinaryIO, None, None]:
        """Yields self._fh and resets to its original position upon exit."""
        pos = self._fh.tell()
        try:
            yield self._fh
        finally:
            self._fh.seek(pos)

    def _clear_read_cache(self) -> None:
        # Deletes all of the @cached_property values.
        for k, v in self.__class__.__dict__.items():
            if v.__class__.__name__ == "cached_property":
                try:
                    delattr(self, k)
                except AttributeError:
                    pass

    @cached_property
    def ident(self) -> ElfIdent:
        with self._peek() as fh:
            fh.seek(0)
            ident = ElfIdent.from_fileobj(fh)
        if (ident.ei_mag0, ident.ei_mag1, ident.ei_mag2, ident.ei_mag3) != ELF_MAGIC:
            raise ValueError("Not an ELF file")
        return ident

    @cached_property
    def ehdr(self) -> Elf_Ehdr:
        with self._peek() as fh:
            fh.seek(0)
            return self._class.Ehdr.from_fileobj(fh)

    @cached_property
    def phdrs(self) -> List[Elf_Phdr]:
        h = self.ehdr
        # Sanity check header size
        if h.e_phentsize != sizeof(self._class.Phdr):
            raise ValueError(f"ELF Phdr entry size ({h.e_phentsize}) doesn't match expected ({sizeof(self._class.Phdr)})")

        if not h.e_phoff:
            return []

        result = []
        entry_count = h.e_phnum
        with self._peek() as fh:
            fh.seek(h.e_phoff)

            for _ in range(entry_count):
                result.append(self._class.Phdr.from_fileobj(fh))

        return result

    @cached_property
    def shdrs(self) -> List[Elf_Shdr]:
        h = self.ehdr

        # Sanity check header size
        if h.e_shentsize != sizeof(self._class.Shdr):
            raise ValueError(f"ELF Shdr entry size ({h.e_shentsize}) doesn't match expected ({sizeof(self._class.Shdr)})")

        if not h.e_shoff:
            return []

        result = []
        entry_count = h.e_shnum
        with self._peek() as fh:
            fh.seek(h.e_shoff)

            if not entry_count:
                # If the number of sections is greater than or equal to SHN_LORESERVE (0xff00),
                # e_shnum has the value zero. The actual number of section header table entries
                # is contained in the sh_size field of the section header at index 0. Otherwise,
                # the sh_size member of the initial section header entry contains the value zero.
                first_entry = self._class.Shdr.from_fileobj(fh)
                entry_count = first_entry.sh_size - 1  # We already read the first entry
                result.append(first_entry)

            for _ in range(entry_count):
                result.append(self._class.Shdr.from_fileobj(fh))

        return result

    @cached_property
    def shdr_names(self) -> List[bytes]:
        ehdr = self.ehdr
        shdrs = self.shdrs
        strtab_off = shdrs[ehdr.e_shstrndx].sh_offset
        result = []
        with self._peek() as fh:
            for shdr in shdrs:
                name_pos = strtab_off + shdr.sh_name
                fh.seek(name_pos)
                result.append(read_c_str(fh))

        return result

    @cached_property
    def dyn(self) -> List[Elf_Dyn]:
        for shdr in self.shdrs:
            if shdr.sh_type == SHT_DYNAMIC:
                dyn_pos = shdr.sh_offset
                break
        else:
            return []  # No dynamic section?

        result = []
        with self._peek() as fh:
            fh.seek(dyn_pos)
            while True:
                next = self._class.Dyn.from_fileobj(fh)
                result.append(next)
                if next.d_tag == DT_NULL:
                    break

        return result

    @cached_property
    def dynstr(self) -> bytes:
        # Find dynstr
        dynstr_pos = -1
        dynstr_size = -1
        for d in self.dyn:
            if d.d_tag == DT_STRTAB:
                dynstr_pos = d.d_ptr_or_val
            elif d.d_tag == DT_STRSZ:
                dynstr_size = d.d_ptr_or_val

        # Sanity check to make sure the .dynstr section agrees with DT_STRTAB and DT_STRSZ.
        dynstr_shdr = self.get_shdr(b".dynstr")
        if dynstr_pos != dynstr_shdr.sh_addr or dynstr_size != dynstr_shdr.sh_size:
            raise ValueError("DT_STRTAB and DT_STRSZ do not agree with .dynstr")

        with self._peek() as fh:
            fh.seek(dynstr_shdr.sh_offset)
            dynstr = fh.read(dynstr_shdr.sh_size)

        return dynstr

    @cached_property
    def verneed_entries(self) -> List[VerneedEntry]:
        verneed_num = None
        for d in self.dyn:
            if d.d_tag == DT_VERNEEDNUM:
                verneed_num = d.d_ptr_or_val

        result = []
        verneed_shdr = self.find_shdr(b".gnu.version_r")
        if verneed_num and verneed_shdr:
            verneed_pos = verneed_shdr.sh_offset
            # We get the string table index from the corresponding verneed section's sh_link
            verneed_strtab_shdr = self.shdrs[verneed_shdr.sh_link]
            with self._peek() as fh:
                fh.seek(verneed_strtab_shdr.sh_offset)
                vn_strtab = fh.read(verneed_strtab_shdr.sh_size)
                while verneed_num:
                    fh.seek(verneed_pos)
                    cur_need = self._class.Verneed.from_fileobj(fh)
                    cur_need_name = get_strtab_entry(vn_strtab, cur_need.vn_file)
                    aux = []
                    aux_names = []
                    aux_count = cur_need.vn_cnt
                    aux_pos = verneed_pos + cur_need.vn_aux
                    while aux_count:
                        fh.seek(aux_pos)
                        cur_aux = self._class.Vernaux.from_fileobj(fh)
                        cur_aux_name = get_strtab_entry(vn_strtab, cur_aux.vna_name)
                        aux_pos += cur_aux.vna_next
                        aux_count -= 1
                        aux.append(cur_aux)
                        aux_names.append(cur_aux_name)

                    result.append(
                        VerneedEntry(verneed=cur_need, vernaux=aux, verneed_name=cur_need_name, vernaux_names=aux_names)
                    )
                    verneed_pos += cur_need.vn_next
                    verneed_num -= 1

        return result

    @cached_property
    def rpath(self) -> Optional[str]:
        for d in self.dyn:
            if d.d_tag == DT_RPATH:
                return get_strtab_entry(self.dynstr, d.d_ptr_or_val)
        return None

    @cached_property
    def runpath(self) -> Optional[bytes]:
        for d in self.dyn:
            if d.d_tag == DT_RUNPATH:
                return get_strtab_entry(self.dynstr, d.d_ptr_or_val)
        return None

    def guess_page_size(self) -> int:
        """Guess the page size from existing PT_LOAD headers. Else default to 0x1000."""
        page_size = 0

        for phdr in self.phdrs:
            if phdr.p_type == PT_LOAD:
                page_size = max(page_size, phdr.p_align)

        # Default to 0x1000
        return page_size or 0x1000

    def _write_dynstr(self, buf: BinaryIO, pos: PositionTracker, dynstr: Dynstr) -> SectionInfo:
        shdr_dynstr = self.get_shdr(b".dynstr")
        pos.round(shdr_dynstr.sh_addralign)
        dynstr_pos = SectionInfo(pos.file_offset, pos.vm_offset, len(dynstr.strtab))
        buf.seek(pos.buf_offset)
        buf.write(dynstr.strtab)
        pos.add(len(dynstr.strtab))
        return dynstr_pos

    def _write_verneed(
        self, buf: BinaryIO, pos: PositionTracker, dynstr: Dynstr, needed_replacements: Dict[bytes, bytes]
    ) -> SectionInfo:
        shdr_verneed = self.get_shdr(b".gnu.version_r")
        pos.round(shdr_verneed.sh_addralign)
        verneed_file_offset = pos.file_offset
        verneed_vm_offset = pos.vm_offset
        verneed_entries = self.verneed_entries

        buf.seek(pos.buf_offset)
        buf_start = buf.tell()
        for vn_index, vn in enumerate(verneed_entries):
            vn_struct = copy.deepcopy(vn.verneed)  # copy because we're going to modify it.
            new_name = needed_replacements.get(vn.verneed_name, vn.verneed_name)
            vn_struct.vn_file = dynstr.needed_pos[new_name]
            if vn.vernaux:
                vn_struct.vn_aux = sizeof(self._class.Verneed)
            else:
                vn_struct.vn_aux = 0
            if vn_index < len(verneed_entries) - 1:
                vn_struct.vn_next = sizeof(self._class.Verneed) + sizeof(self._class.Vernaux) * len(vn.vernaux)
            else:
                vn_struct.vn_next = 0
            vn_struct.to_fileobj(buf)

            for vna_index, (vna_struct, vna_name) in enumerate(zip(vn.vernaux, vn.vernaux_names)):
                vna_struct = copy.deepcopy(vna_struct)
                vna_struct.vna_name = dynstr.vernaux_pos[vna_name]
                if vna_index < len(vn.vernaux) - 1:
                    vna_struct.vna_next = sizeof(self._class.Vernaux)
                else:
                    vna_struct.vna_next = 0
                vna_struct.to_fileobj(buf)

        written_len = buf.tell() - buf_start
        pos.add(written_len)

        return SectionInfo(verneed_file_offset, verneed_vm_offset, written_len, len(verneed_entries))

    def _write_dynamic(
        self,
        buf: BinaryIO,
        pos: PositionTracker,
        dynstr: Dynstr,
        soname: bytes,
        rpath: bytes,
        needed: List[bytes],
        dynstr_pos: SectionInfo,
        verneed_pos: Optional[SectionInfo],
    ) -> SectionInfo:
        shdr_dynamic = self.get_shdr(b".dynamic")
        pos.round(shdr_dynamic.sh_addralign)
        dyn_file_offset = pos.file_offset
        dyn_vm_offset = pos.vm_offset

        buf.seek(pos.buf_offset)
        buf_start = buf.tell()

        # Write out all of the entries that we're not mucking with first.
        # TODO: Handle DT_MIPS_RLD_MAP_REL. https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=820334#5
        for d in self.dyn:
            if d.d_tag not in [
                DT_STRTAB,
                DT_STRSZ,
                DT_NEEDED,
                DT_SONAME,
                DT_RPATH,
                DT_RUNPATH,
                DT_VERNEED,
                DT_VERNEEDNUM,
                DT_NULL,
            ]:
                d.to_fileobj(buf)

        self._class.Dyn(
            d_tag=DT_STRTAB,
            d_ptr_or_val=dynstr_pos.vm_offset,
        ).to_fileobj(buf)

        self._class.Dyn(
            d_tag=DT_STRSZ,
            d_ptr_or_val=dynstr_pos.length,
        ).to_fileobj(buf)

        if soname:
            self._class.Dyn(
                d_tag=DT_SONAME,
                d_ptr_or_val=dynstr.soname_pos,
            ).to_fileobj(buf)

        if rpath:
            self._class.Dyn(
                d_tag=DT_RPATH,
                d_ptr_or_val=dynstr.rpath_pos,
            ).to_fileobj(buf)

        for needed_name in needed:
            self._class.Dyn(
                d_tag=DT_NEEDED,
                d_ptr_or_val=dynstr.needed_pos[needed_name],
            ).to_fileobj(buf)

        if verneed_pos:
            self._class.Dyn(
                d_tag=DT_VERNEED,
                d_ptr_or_val=verneed_pos.vm_offset,
            ).to_fileobj(buf)

            self._class.Dyn(
                d_tag=DT_VERNEEDNUM,
                d_ptr_or_val=verneed_pos.count,
            ).to_fileobj(buf)

        # End the section with DT_NULL
        self._class.Dyn(
            d_tag=DT_NULL,
            d_ptr_or_val=0,
        ).to_fileobj(buf)

        written_len = buf.tell() - buf_start
        pos.add(written_len)

        return SectionInfo(dyn_file_offset, dyn_vm_offset, written_len)

    def _write_shdrs(
        self,
        buf: BinaryIO,
        pos: PositionTracker,
        dynstr_pos: SectionInfo,
        dynamic_pos: SectionInfo,
        verneed_pos: Optional[SectionInfo],
    ) -> SectionInfo:
        pos.round(self._class.alignment)
        shdr_file_offset = pos.file_offset
        shdr_vm_offset = pos.vm_offset

        buf.seek(pos.buf_offset)
        buf_start = buf.tell()

        dynstr_index = self.shdr_names.index(b".dynstr")  # We'll use this for sh_link in .dynamic and .gnu.version_r

        for shdr, shdr_name in zip(self.shdrs, self.shdr_names):
            shdr = copy.deepcopy(shdr)
            if shdr_name == b".dynstr":
                shdr.sh_addr = dynstr_pos.vm_offset
                shdr.sh_offset = dynstr_pos.file_offset
                shdr.sh_size = dynstr_pos.length
            elif shdr_name == b".dynamic":
                shdr.sh_addr = dynamic_pos.vm_offset
                shdr.sh_offset = dynamic_pos.file_offset
                shdr.sh_size = dynamic_pos.length
                shdr.sh_link = dynstr_index
            elif shdr_name == b".gnu.version_r":
                shdr.sh_addr = verneed_pos.vm_offset
                shdr.sh_offset = verneed_pos.file_offset
                shdr.sh_size = verneed_pos.length
                shdr.sh_link = dynstr_index
                shdr.sh_info = verneed_pos.count

            shdr.to_fileobj(buf)

        written_len = buf.tell() - buf_start
        pos.add(written_len)

        return SectionInfo(shdr_file_offset, shdr_vm_offset, written_len, len(self.shdrs))

    def _write_phdrs(self, buf: BinaryIO, pos: PositionTracker, dynamic_pos: SectionInfo, add_new_load: bool) -> SectionInfo:
        pos.round(self._class.alignment)
        phdr_file_offset = pos.file_offset
        phdr_vm_offset = pos.vm_offset

        buf.seek(pos.buf_offset)
        buf_start = buf.tell()

        phdr_count = len(self.phdrs)
        for phdr in self.phdrs:
            phdr = copy.deepcopy(phdr)
            if phdr.p_type == PT_DYNAMIC:
                phdr.p_offset = dynamic_pos.file_offset
                phdr.p_vaddr = dynamic_pos.vm_offset
                phdr.p_paddr = dynamic_pos.vm_offset
                phdr.p_filesz = dynamic_pos.length
                phdr.p_memsz = dynamic_pos.length
            elif phdr.p_type == PT_PHDR:
                phdr_size = sizeof(self._class.Phdr) * phdr_count
                if add_new_load:
                    phdr_size += sizeof(self._class.Phdr)
                phdr.p_offset = phdr_file_offset
                phdr.p_vaddr = phdr_vm_offset
                phdr.p_paddr = phdr_vm_offset
                phdr.p_filesz = phdr_size
                phdr.p_memsz = phdr_size

            phdr.to_fileobj(buf)

        written_len = buf.tell() - buf_start
        pos.add(written_len)

        # We may need to add an additional PT_LOAD for our patches.
        if add_new_load:
            pos.add(sizeof(self._class.Phdr))
            written_len += sizeof(self._class.Phdr)
            phdr_count += 1

            page_size = self.guess_page_size()
            self._class.Phdr(
                p_type=PT_LOAD,
                p_flags=PF_R | PF_W,
                p_offset=pos.file_start,
                p_vaddr=pos.vm_start,
                p_paddr=pos.vm_start,
                p_filesz=pos.file_size,
                p_memsz=pos.vm_size,
                p_align=page_size,
            ).to_fileobj(buf)

        return SectionInfo(phdr_file_offset, phdr_vm_offset, written_len, phdr_count)

    def _write_new_trailer(
        self,
        buf: BinaryIO,
        file_offset: int,
        vm_offset: int,
        new_soname: Optional[bytes] = None,
        new_rpath: Optional[bytes] = None,
        needed_replacements: Optional[Dict[bytes, bytes]] = None,
        add_new_load: bool = False,
        place_phdrs_at_start_of_section: bool = False,
    ) -> Tuple[SectionInfo, SectionInfo]:
        needed_replacements = needed_replacements or {}
        cur_needed_names = []
        cur_rpath = b""
        cur_runpath = b""
        cur_soname = b""
        for d in self.dyn:
            if d.d_tag == DT_NEEDED:
                cur_needed_names.append(get_strtab_entry(self.dynstr, d.d_ptr_or_val))
            elif d.d_tag == DT_SONAME:
                cur_soname = get_strtab_entry(self.dynstr, d.d_ptr_or_val)
            elif d.d_tag == DT_RPATH:
                cur_rpath = get_strtab_entry(self.dynstr, d.d_ptr_or_val)
            elif d.d_tag == DT_RUNPATH:
                cur_runpath = get_strtab_entry(self.dynstr, d.d_ptr_or_val)

        cur_verneed_names = [ve.verneed_name for ve in self.verneed_entries]
        all_verneed_versions = {aux for ve in self.verneed_entries for aux in ve.vernaux_names}

        # Unpatched binaries might have runpath, which takes precedence over rpath.
        # After patching, we'll have removed the runpath.
        if cur_runpath:
            cur_rpath = cur_runpath

        # If new values weren't specified, we'll rewrite the current values.
        new_soname = new_soname or cur_soname
        new_rpath = new_rpath or cur_rpath

        # Update our DT_NEEDED and DT_VERNEED lists
        new_needed_names = [needed_replacements.get(e, e) for e in cur_needed_names]
        new_verneed_names = [needed_replacements.get(e, e) for e in cur_verneed_names]

        # Next we need to figure out if we can replace the end of .dynstr.
        # We expect .dynstr to end with a substring starting with $PATCH$\0,
        # followed by our SONAME, RPATH, and needed paths (shared between
        # DT_NEEDED and DT_VERNEED). If not, we just append to .dynstr and leave
        # everything else.
        expected_dynstr_suffix = build_dynstr(
            cur_soname, cur_rpath, set(cur_needed_names + cur_verneed_names), all_verneed_versions
        )

        # See if .dynstr ends with what we expect. If there's stuff before our prefix, we expect
        # a null byte that follows the last existing entry.
        if self.dynstr == expected_dynstr_suffix.strtab or self.dynstr.endswith(b"\0" + expected_dynstr_suffix.strtab):
            new_dynstr_prefix = self.dynstr[: -len(expected_dynstr_suffix.strtab)]
        else:
            new_dynstr_prefix = self.dynstr

        # Construct the new .dynstr on top of whatever prefix we determined.
        new_dynstr = build_dynstr(
            new_soname, new_rpath, set(new_needed_names + new_verneed_names), all_verneed_versions, prefix=new_dynstr_prefix
        )

        # Now we can write to our new buffer
        pos = PositionTracker(file_offset, vm_offset)

        if place_phdrs_at_start_of_section:
            # write the PHDRS section with some mock data, just to take up the
            # proper amount of space. We'll come back and overwrite at the end.
            self._write_phdrs(buf, pos, SectionInfo(0, 0, 0), add_new_load)

        # .dynstr
        dynstr_pos = self._write_dynstr(buf, pos, new_dynstr)

        # .gnu.version_r
        if self.verneed_entries:
            verneed_pos = self._write_verneed(buf, pos, new_dynstr, needed_replacements)
        else:
            verneed_pos = None

        # .dynamic
        dynamic_pos = self._write_dynamic(
            buf, pos, new_dynstr, new_soname, new_rpath, new_needed_names, dynstr_pos, verneed_pos
        )

        # shdrs
        shdr_pos = self._write_shdrs(buf, pos, dynstr_pos, dynamic_pos, verneed_pos)

        # phdrs
        if place_phdrs_at_start_of_section:
            pos.back_to_start()
        phdr_pos = self._write_phdrs(buf, pos, dynamic_pos, add_new_load)

        return phdr_pos, shdr_pos, dynamic_pos

    def _update_dynamic_symbol(self, dynamic_pos: PositionTracker) -> None:
        symtab_shdr = self.find_shdr(b".symtab")
        if not symtab_shdr:
            return

        # We get the string table index from the corresponding symtab section's sh_link
        strtab_shdr = self.shdrs[symtab_shdr.sh_link]
        with self._peek() as fh:
            fh.seek(strtab_shdr.sh_offset)
            st_strtab = fh.read(strtab_shdr.sh_size)
            count = symtab_shdr.sh_size // sizeof(self._class.Sym)
            for i in range(count):
                pos = symtab_shdr.sh_offset + i * sizeof(self._class.Sym)
                fh.seek(pos)
                entry = self._class.Sym.from_fileobj(fh)
                if entry.st_name != 0:
                    name = get_strtab_entry(st_strtab, entry.st_name)
                    if name == b"_DYNAMIC":
                        entry = copy.deepcopy(entry)
                        entry.st_value = dynamic_pos.vm_offset
                        fh.seek(pos)
                        entry.to_fileobj(fh)
                        return

    def get_shdr(self, name: bytes) -> Elf_Shdr:
        s = self.find_shdr(name)
        if not s:
            raise ValueError("Section not found: " + name.decode("utf-8"))
        return s

    def find_shdr(self, name: bytes) -> Optional[Elf_Shdr]:
        assert isinstance(name, bytes), "expected name to be of type bytes"
        for shdr, shdr_name in zip(self.shdrs, self.shdr_names):
            if shdr_name == name:
                return shdr
        return None

    def _get_last_load_segment(self) -> Optional[Elf_Phdr]:
        last_load = None
        for phdr in self.phdrs:
            if phdr.p_type == PT_LOAD:
                if last_load is None or phdr.p_offset > last_load.p_offset:
                    last_load = phdr
        return last_load

    def _can_overwrite_last_load(self, last_load_header: Elf_Phdr) -> bool:
        with self._peek() as fh:
            fh.seek(last_load_header.p_offset)
            last_load_data = fh.read(last_load_header.p_filesz)
            read_end = fh.tell()
            fh.seek(0, 2)
            file_end = fh.tell()

        # Return false if this isn't the last data in the file
        if read_end != file_end:
            return False

        # Generate the LOAD segment that we'd expect with the current values, and
        # compare against what actually exists.
        new_load_data = io.BytesIO()
        self._write_new_trailer(
            buf=new_load_data,
            file_offset=last_load_header.p_offset,
            vm_offset=last_load_header.p_vaddr,
            add_new_load=False,
        )
        return new_load_data.getvalue() == last_load_data

    def rewrite(
        self,
        new_soname: Optional[bytes] = None,
        new_rpath: Optional[bytes] = None,
        needed_replacements: Optional[Dict[bytes, bytes]] = None,
    ) -> None:
        if self.ehdr.e_type != ET_DYN:
            raise ValueError("Not a dynamic file (ET_DYN)")

        needed_replacements = needed_replacements or {}

        self._fh.seek(0, 2)
        file_end = self._fh.tell()
        page_size = self.guess_page_size()

        last_load_header = self._get_last_load_segment()
        assert last_load_header, "File has no LOAD segments!"

        if self._can_overwrite_last_load(last_load_header):
            new_offset = last_load_header.p_offset
            new_vm_offset = last_load_header.p_vaddr
            add_new_load = False
        else:
            vm_max = last_load_header.p_vaddr + last_load_header.p_memsz
            # Our first section will be the PHDRs which are aligned to Elf_Off.
            new_offset = round_to_multiple(file_end, page_size)
            # Then make our vm addr match
            new_vm_offset = congruent_vm_addr(new_offset, vm_max, page_size)
            add_new_load = True

        buf = io.BytesIO()
        phdr_pos, shdr_pos, dynamic_pos = self._write_new_trailer(
            buf=buf,
            file_offset=new_offset,
            vm_offset=new_vm_offset,
            new_soname=new_soname,
            new_rpath=new_rpath,
            needed_replacements=needed_replacements,
            add_new_load=add_new_load,
        )

        if add_new_load:
            # Zero pad to the start of our new page
            fzero(self._fh, file_end, new_offset - file_end)

        self._fh.seek(new_offset)
        self._fh.write(buf.getbuffer())

        # In case we're overwriting an existing segment, truncate any remaining garbage.
        self._fh.truncate(self._fh.tell())

        self._update_dynamic_symbol(dynamic_pos)

        hdr = copy.deepcopy(self.ehdr)
        hdr.e_phoff = phdr_pos.file_offset
        hdr.e_phnum = phdr_pos.count
        hdr.e_shoff = shdr_pos.file_offset
        hdr.e_shnum = shdr_pos.count
        self._fh.seek(0)
        hdr.to_fileobj(self._fh)

        self._clear_read_cache()


def read_c_str(fh: BinaryIO) -> bytes:
    start = fh.tell()
    data = b""
    while True:
        read = fh.read(32)  # read 32 bytes at a time
        if not read:
            # Just return what we have.
            return data

        data += read
        null_pos = data.find(0)
        if null_pos >= 0:
            data = data[:null_pos]
            fh.seek(start + len(data) + 1)  # Seek after the null
            break

    return data


def get_strtab_entry(strtab: bytes, start: int) -> bytes:
    end = start
    while end < len(strtab) and strtab[end] != 0:
        end += 1
    return strtab[start:end]


def build_dynstr(soname: bytes, rpath: bytes, needed: Set[bytes], vernaux_versions: Set[bytes], prefix=b"") -> Dynstr:
    result = prefix + b"$PATCH$\0"
    soname_pos = len(result)
    result += soname + b"\0"
    rpath_pos = len(result)
    result += rpath + b"\0"

    needed_pos = {}
    for needed_entry in sorted(needed):
        needed_pos[needed_entry] = len(result)
        result += needed_entry + b"\0"

    vernaux_pos = {}
    for vernaux_entry in sorted(vernaux_versions):
        vernaux_pos[vernaux_entry] = len(result)
        result += vernaux_entry + b"\0"

    return Dynstr(result, soname_pos, rpath_pos, needed_pos, vernaux_pos)


def congruent_vm_addr(file_offset: int, vm_start: int, page_size: int) -> int:
    """Returns the vm addr >= vm_start where file_offset % page_size == val % page_size"""
    fmod = file_offset % page_size
    vmod = vm_start % page_size
    if vmod < fmod:
        return vm_start + (fmod - vmod)
    elif vmod > fmod:
        return vm_start + (page_size - (vmod - fmod))
    else:
        return vm_start


if __name__ == "__main__":
    import sys

    with open(sys.argv[1], "r+b") as f:
        ef = ElfFile(f)
        ef.rewrite(new_soname=b"foojfkdlsjklfjdskjfkdslfds")
        ef.rewrite(new_rpath=b"/tmp")
        ef.rewrite(new_soname=b"foo")
        ef.rewrite(new_soname=b"foobar")
