import hashlib
import io
import logging
import math
from typing import List
from macholib.MachO import MachO
from macholib.ptypes import Structure
from macholib.ptypes import p_uint8
from macholib.ptypes import p_uint32
from macholib.ptypes import p_uint64
from macholib.ptypes import sizeof

from .fileutil import open_create


# https://developer.apple.com/documentation/technotes/tn3126-inside-code-signing-hashes
# https://github.com/thefloweringash/sigtool/blob/main/README.md
# https://github.com/qyang-nj/llios/blob/main/macho_parser/docs/LC_CODE_SIGNATURE.md
# https://medium.com/csit-tech-blog/demystifying-ios-code-signature-309d52c2ff1d

LOG = logging.getLogger(__name__)

CODE_DIRECTORY_PAGE_SIZE = 4096  # Seems to be what Apple always uses
SHA256_HASH_SIZE = 32

CSMAGIC_REQUIREMENT = 0xFADE0C00  # single Requirement blob
CSMAGIC_REQUIREMENTS = 0xFADE0C01  # Requirements vector (internal requirements)
CSMAGIC_CODEDIRECTORY = 0xFADE0C02  # CodeDirectory blob
CSMAGIC_EMBEDDED_SIGNATURE = 0xFADE0CC0  # embedded form of signature data
CSMAGIC_DETACHED_SIGNATURE = 0xFADE0CC1  # multi-arch collection of embedded signatures
CSMAGIC_BLOBWRAPPER = 0xFADE0B01  # used for the cms blob

CSSLOT_CODEDIRECTORY = 0  # slot index for CodeDirectory
CSSLOT_INFOSLOT = 1
CSSLOT_REQUIREMENTS = 2
CSSLOT_RESOURCEDIR = 3
CSSLOT_APPLICATION = 4
CSSLOT_ENTITLEMENTS = 5
CSSLOT_SIGNATURESLOT = 0x10000

CS_ADHOC = 0x2

CS_HASHTYPE_SHA256 = 2

CS_EXECSEG_MAIN_BINARY = 0x1


class cs_blob_index(Structure):
    _endian_ = ">"
    _fields_ = [
        ("type", p_uint32),  # type of entry
        ("offset", p_uint32),  # offset of entry
    ]


class cs_super_blob(Structure):
    _endian_ = ">"
    _fields_ = [
        ("magic", p_uint32),
        ("length", p_uint32),
        ("count", p_uint32),
    ]


class cs_generic_blob(Structure):
    _endian_ = ">"
    _fields_ = [
        ("magic", p_uint32),
        ("length", p_uint32),
    ]


class cs_code_directory(Structure):
    _endian_ = ">"

    # Fields below marked as ">= version" will be garbage when read from a
    # lower-versioned structure.
    _fields_ = [
        ("magic", p_uint32),  # magic number (CSMAGIC_CODEDIRECTORY)
        ("length", p_uint32),  # total length of CodeDirectory blob
        ("version", p_uint32),  # compatibility version
        ("flags", p_uint32),  # setup and mode flags
        ("hashoffset", p_uint32),  # offset of hash slot element at index zero
        ("identoffset", p_uint32),  # offset of identifier string
        ("nspecialslots", p_uint32),  # number of special hash slots
        ("ncodeslots", p_uint32),  # number of ordinary (code) hash slots
        ("codelimit", p_uint32),  # limit to main image signature range
        ("hashsize", p_uint8),  # size of each hash in bytes
        ("hashtype", p_uint8),  # type of hash (cdHashType* constants)
        ("platform", p_uint8),  # platform identifier; zero if not platform binary
        ("pagesize", p_uint8),  # log2(page size in bytes); 0 => infinite
        ("spare2", p_uint32),  # unused (must be zero)
        # Version >= 0x20100
        ("scatteroffset", p_uint32),  # offset of optional scatter vector
        # Version >= 0x20200
        ("teamoffset", p_uint32),  # offset of optional team identifier
        # Version >= 0x20300
        ("spare3", p_uint32),  # unused (must be zero)
        ("codelimit64", p_uint64),  # limit to main image signature range, 64 bits
        # Version >= 0x20400
        ("execsegbase", p_uint64),  # offset of executable segment
        ("execseglimit", p_uint64),  # limit of executable segment
        ("execsegflags", p_uint64),  # executable segment flags
    ]


class cs_requirements_blob(Structure):
    _endian_ = ">"
    _fields_ = [
        ("magic", p_uint32),
        ("length", p_uint32),
        ("data", p_uint32),
    ]


def log2(val: int) -> int:
    return int(math.log2(val))


def _gen_signature(
    page_hashes: List[bytes], identifier: str, code_limit: int, exec_start: int, exec_end: int, is_executable: bool
) -> bytes:
    # Generate an empty requirements blob and its hash, which we'll use later.
    requirements_bytes = cs_requirements_blob(
        magic=CSMAGIC_REQUIREMENTS,
        length=sizeof(cs_requirements_blob),
        data=0,
    ).to_str()
    requirements_hash = hashlib.sha256(requirements_bytes).digest()
    assert len(requirements_hash) == SHA256_HASH_SIZE

    # Generate the code directory
    dir = cs_code_directory(
        magic=CSMAGIC_CODEDIRECTORY,
        version=0x20400,
        flags=CS_ADHOC,
        nspecialslots=2,  # Just the requirements blob + empty Info.plist hash
        ncodeslots=len(page_hashes),
        hashsize=SHA256_HASH_SIZE,
        hashtype=CS_HASHTYPE_SHA256,
        platform=0,
        pagesize=log2(CODE_DIRECTORY_PAGE_SIZE),
        spare2=0,
        scatteroffset=0,
        teamoffset=0,
        spare3=0,
        execsegbase=exec_start,
        execseglimit=exec_end,
        execsegflags=CS_EXECSEG_MAIN_BINARY if is_executable else 0,
    )

    if code_limit <= 2**32:
        dir.codelimit = code_limit
        dir.codelimit64 = 0
    else:
        dir.codelimit = 0
        dir.codelimit64 = code_limit

    dir_io = io.BytesIO()

    # Skip over the CD structure while we write the data after it.
    dir_io.seek(sizeof(cs_code_directory))

    # Write the identifier string
    dir.identoffset = dir_io.tell()
    dir_io.write(identifier.encode("utf-8"))
    dir_io.write(b'\0')  # null terminator

    # Write our two special hashes: the requirements hash and the null Info.plist hash
    dir_io.write(requirements_hash)
    dir_io.write(b'\0' * SHA256_HASH_SIZE)

    # Record the offset to the first code page hash
    dir.hashoffset = dir_io.tell()
    for page_hash in page_hashes:
        assert len(page_hash) == SHA256_HASH_SIZE
        dir_io.write(page_hash)

    # Now we know the final length
    dir.length = dir_io.tell()
    dir_io.seek(0)
    dir.to_fileobj(dir_io)

    dir_bytes = dir_io.getvalue()

    # Generate the trailing wrapper bytes
    wrapper_bytes = cs_generic_blob(
        magic=CSMAGIC_BLOBWRAPPER,
        length=sizeof(cs_generic_blob),
    ).to_str()

    # Now we generate the full super blob structure
    super = cs_super_blob(
        magic=CSMAGIC_EMBEDDED_SIGNATURE,
        count=3,  # code directory, requirements, wrapper
    )

    index_dir = cs_blob_index(type=CSSLOT_CODEDIRECTORY)
    index_requirements = cs_blob_index(type=CSSLOT_REQUIREMENTS)
    index_wrapper = cs_blob_index(type=CSSLOT_SIGNATURESLOT)

    super_io = io.BytesIO()
    super_io.seek(sizeof(cs_super_blob) + 3 * sizeof(cs_blob_index))  # 3 index entries for our three blobs

    # First write the indexes for our blobs.
    index_dir.offset = super_io.tell()
    super_io.write(dir_bytes)

    index_requirements.offset = super_io.tell()
    super_io.write(requirements_bytes)

    index_wrapper.offset = super_io.tell()
    super_io.write(wrapper_bytes)

    super.length = super_io.tell()

    # Now write the super blob header and index entries
    super_io.seek(0)
    super.to_fileobj(super_io)
    index_dir.to_fileobj(super_io)
    index_requirements.to_fileobj(super_io)
    index_wrapper.to_fileobj(super_io)

    return super_io.getvalue()


def _calc_signature_length(identifier: str, code_limit: int) -> int:
    # Maybe unnecessarily expensive, but the easiest way to calculate the signature length
    # is to generate it with null data and count.
    num_pages = math.ceil(code_limit / CODE_DIRECTORY_PAGE_SIZE)
    null_hashes = [b'\0' * SHA256_HASH_SIZE] * num_pages
    bytes = _gen_signature(
        page_hashes=null_hashes,
        identifier=identifier,
        code_limit=code_limit,
        exec_start=0,
        exec_end=0,
        is_executable=False,
    )
    return len(bytes)


def ad_hoc_sign(filename: str) -> None:
    macho = MachO(filename)
    with open(filename, 'r+', opener=open_create) as fh:
        fh.seek(0)
        if macho.fat:
            # MachO doesn't hold on to the FAT specifics, so we read them again
            pass


def validate_signature(filename: str) -> None:
    """Remove invalid signatures from a binary file

    If the file signature is missing or valid then it will be ignored

    Invalid signatures are replaced with an ad-hoc signature.  This is the
    closest you can get to removing a signature on MacOS

    Parameters
    ----------
    filename : str
        Filepath to a binary file
    """
    raise NotImplementedError
