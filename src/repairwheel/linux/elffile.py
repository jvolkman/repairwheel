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
ELF_MAGIC = (0x7f, ord("E"), ord("L"), ord("F"))

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


class Elf32_Ehdr(Structure):
    _fields_ = ElfIdent._fields_ + [
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


class Elf64_Ehdr(Structure):
    _fields_ = ElfIdent._fields_ + [
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


class Elf32_Phdr(Structure):
    _fields_ = [
        ("p_type", Elf32_Word),
        ("p_offset", Elf32_Off),
        ("p_vaddr", Elf32_Addr),
        ("p_paddr", Elf32_Addr),
        ("p_filesz", Elf32_Word),
        ("p_memsz", Elf32_Word),
        ("p_flags", Elf32_Word),
        ("p_align", Elf32_Word),
    ]


class Elf64_Phdr(Structure):
    _fields_ = [
        ("p_type", Elf64_Word),
        ("p_flags", Elf64_Word),
        ("p_offset", Elf64_Off),
        ("p_vaddr", Elf64_Addr),
        ("p_paddr", Elf64_Addr),
        ("p_filesz", Elf64_Xword),
        ("p_memsz", Elf64_Xword),
        ("p_align", Elf64_Xword),
    ]


class Elf32_Shdr(Structure):
    _fields_ = [
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


class Elf64_Shdr(Structure):
    _fields_ = [
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


Elf_Ehdr = Union[Elf32_Ehdr, Elf64_Ehdr]
Elf_Phdr = Union[Elf32_Phdr, Elf64_Phdr]
Elf_Shdr = Union[Elf32_Shdr, Elf64_Shdr]


@dataclass
class ElfClass:
    Ehdr: Elf_Ehdr
    Phdr: Elf_Phdr
    Shdr: Elf_Shdr


ELF32_CLASS = ElfClass(
    Ehdr=Elf32_Ehdr,
    Phdr=Elf32_Phdr,
    Shdr=Elf32_Shdr,
)

ELF64_CLASS = ElfClass(
    Ehdr=Elf64_Ehdr,
    Phdr=Elf64_Phdr,
    Shdr=Elf64_Shdr,
)


# .interp, PT_INTERP
# .dynamic, PT_DYNAMIC
# PT_NOTE
# .MIPS.abiflags, PT_MIPS_ABIFLAGS
# .note.gnu.property, PT_GNU_PROPERTY

# .dynsym

# Move everything down
# insert new LOAD Phdr
# copy DYNAMIC section, change Phdr 



class ElfFile:
    def __init__(self, fh: BinaryIO):
        self._fh = fh

        ident = self.ident
        self.elf_class = ident.ei_class

        if ident.ei_class == ELFCLASS32:
            self._class = ELF32_CLASS
        elif ident.ei_class == ELFCLASS64:
            self._class = ELF64_CLASS
        else:
            raise ValueError(f"Unknown ei_class value: {ident.ei_class}")

        if ident.ei_data == ELFDATA2LSB:
            self._endian = "<"
        elif ident.ei_data == ELFDATA2MSB:
            self._endian = ">"
        else:
            raise ValueError(f"Unknown ei_data value: {ident.ei_data}")

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
            return self._class.Ehdr.from_fileobj(fh, _endian_=self._endian)

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
                result.append(self._class.Phdr.from_fileobj(fh, _endian_=self._endian))

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
                first_entry = self._class.Shdr.from_fileobj(fh, _endian_=self._endian)
                entry_count = first_entry.sh_size - 1  # We already read the first entry
                result.append(first_entry)

            for _ in range(entry_count):
                result.append(self._class.Shdr.from_fileobj(fh, _endian_=self._endian))

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
