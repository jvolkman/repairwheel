from contextlib import contextmanager
from dataclasses import dataclass
from typing import BinaryIO
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

PT_NULL = 0  # Program header table entry unused
PT_LOAD = 1  # Loadable program segment
PT_DYNAMIC = 2  # Dynamic linking information
PT_INTERP = 3  # Program interpreter
PT_NOTE = 4  # Auxiliary information
PT_SHLIB = 5  # Reserved
PT_PHDR = 6  # Entry for header table itself
PT_TLS = 7  # Thread-local storage segment
PT_NUM = 8  # Number of defined types

PF_R = 0x4
PF_W = 0x2
PF_X = 0x1

SHT_STRTAB = 3
SHT_DYNAMIC = 6

DT_NULL = 0
DT_NEEDED = 1
DT_STRTAB = 5
DT_SONAME = 14
DT_RPATH = 15
DT_RUNPATH = 29


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


_Elf32_Ehdr_fields = ElfIdent._fields_ + [
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


_Elf64_Ehdr_fields = ElfIdent._fields_ + [
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


Elf_Ehdr = Union[Elf32_Ehdr_BE, Elf32_Ehdr_LE, Elf64_Ehdr_BE, Elf64_Ehdr_LE]
Elf_Phdr = Union[Elf32_Phdr_BE, Elf32_Phdr_LE, Elf64_Phdr_BE, Elf64_Phdr_LE]
Elf_Shdr = Union[Elf32_Shdr_BE, Elf32_Shdr_LE, Elf64_Shdr_BE, Elf64_Shdr_LE]
Elf_Dyn = Union[Elf32_Dyn_BE, Elf32_Dyn_LE, Elf64_Dyn_BE, Elf64_Dyn_LE]


@dataclass
class ElfClass:
    Ehdr: Elf_Ehdr
    Phdr: Elf_Phdr
    Shdr: Elf_Shdr
    Dyn: Elf_Dyn


ELF32_CLASS_BE = ElfClass(
    Ehdr=Elf32_Ehdr_BE,
    Phdr=Elf32_Phdr_BE,
    Shdr=Elf32_Shdr_BE,
    Dyn=Elf32_Dyn_BE,
)

ELF32_CLASS_LE = ElfClass(
    Ehdr=Elf32_Ehdr_LE,
    Phdr=Elf32_Phdr_LE,
    Shdr=Elf32_Shdr_LE,
    Dyn=Elf32_Dyn_LE,
)

ELF64_CLASS_BE = ElfClass(
    Ehdr=Elf64_Ehdr_BE,
    Phdr=Elf64_Phdr_BE,
    Shdr=Elf64_Shdr_BE,
    Dyn=Elf64_Dyn_BE,
)

ELF64_CLASS_LE = ElfClass(
    Ehdr=Elf64_Ehdr_LE,
    Phdr=Elf64_Phdr_LE,
    Shdr=Elf64_Shdr_LE,
    Dyn=Elf64_Dyn_LE,
)


# Copy phdrs
## Update PT_PHDR
# Copy shdrs
# Copy .dynamic
# Copy .dynstr
# Copy .gnu.version_r

## Update PT_DYNAMIC
## Update SHT_DYNAMIC
### Update SHT_DYNAMIC.sh_link -> index of dynstr
# Update SHT_STRTAB
# Update DT_STRTAB


##


def round_to_multiple(num: int, multiple: int) -> int:
    return ((num + multiple - 1) // multiple) * multiple


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
    def _peek(self) -> BinaryIO:
        """Yields self._fh and resets to its original position upon exit."""
        pos = self._fh.tell()
        yield self._fh
        self._fh.seek(pos)

    @property
    def ident(self) -> ElfIdent:
        with self._peek() as fh:
            fh.seek(0)
            ident = ElfIdent.from_fileobj(fh)
        if (ident.ei_mag0, ident.ei_mag1, ident.ei_mag2, ident.ei_mag3) != ELF_MAGIC:
            raise ValueError("Not an ELF file")
        return ident

    @property
    def ehdr(self) -> Elf_Ehdr:
        with self._peek() as fh:
            fh.seek(0)
            return self._class.Ehdr.from_fileobj(fh)

    @property
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

    @property
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

    @property
    def dyn(self) -> List[Elf_Dyn]:
        shdrs = self.shdrs
        for shdr in shdrs:
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

    def shdr_name(self, index) -> bytes:
        ehdr = self.ehdr
        shdrs = self.shdrs
        strtab_off = shdrs[ehdr.e_shstrndx].sh_offset
        name_pos = strtab_off + self.shdrs[index].sh_name
        with self._peek() as fh:
            fh.seek(name_pos)
            return read_c_str(fh)

    def guess_page_size(self) -> int:
        """Guess the page size from existing PT_LOAD headers. Else default to 0x1000."""
        page_size = 0

        for phdr in self.phdrs:
            if phdr.p_type == PT_LOAD:
                page_size = max(page_size, phdr.p_align)

        # Default to 0x1000
        return page_size or 0x1000

    def relocate_phdrs(self):
        self._fh.seek(0, 2)
        file_end = self._fh.tell()
        page_size = self.guess_page_size()

        phdrs = self.phdrs
        # First pass gets us the upper vmaddr
        vm_max = 0
        for phdr in phdrs:
            vm_end = phdr.p_vaddr + phdr.p_memsz
            if vm_end > vm_max:
                vm_max = vm_end

        new_offset = round_to_multiple(file_end, page_size)
        new_vm_offset = round_to_multiple(vm_max, page_size)

        new_header = self._class.Phdr(
            p_type=PT_LOAD,
            p_flags=PF_R | PF_W,
            p_offset=new_offset,
            p_vaddr=new_vm_offset,
            p_paddr=new_vm_offset,
            p_filesz=page_size,  # TODO: may not be large enough
            p_memsz=page_size,
            p_align=page_size,
        )
        phdrs.append(new_header)

        # # Update the PT_PHDR entry if it exists.
        for phdr in phdrs:
            if phdr.p_type == PT_PHDR:
                phdr.p_offset = new_header.p_offset
                phdr.p_vaddr = new_header.p_vaddr
                phdr.p_paddr = new_header.p_paddr
                phdr.p_filesz = new_header.p_filesz
                phdr.p_memsz = new_header.p_memsz

        # Zero pad to the start of our new page
        fzero(self._fh, file_end, new_offset - file_end)
        self._fh.seek(new_offset)

        # Write the new headers
        for phdr in phdrs:
            phdr.to_fileobj(self._fh)

        hdr = self.ehdr
        hdr.e_phoff = new_offset
        hdr.e_phnum = len(phdrs)
        self._fh.seek(0)
        hdr.to_fileobj(self._fh)


def read_c_str(fh: BinaryIO) -> bytes:
    start = fh.tell()
    data = b""
    while True:
        read = fh.read(32)  # read 32 bytes at a time
        if not read:
            # Just return what we have.
            return data

        data += read
        null_pos = data.find(b"\0")
        if null_pos >= 0:
            data = data[:null_pos]
            fh.seek(start + len(data) + 1)  # Seek after the null
            break

    return data


if __name__ == "__main__":
    import sys

    with open(sys.argv[1], "r+b") as f:
        ef = ElfFile(f)
        ef.relocate_phdrs()
