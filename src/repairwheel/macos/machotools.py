import logging
from typing import Callable
from typing import FrozenSet
from typing import Optional
from typing import Tuple
from typing import TypeVar
from macholib.MachO import MachO
from macholib.MachO import MachOHeader
from macholib.MachO import lc_str_value
from macholib.mach_o import CPU_TYPE_NAMES
from macholib.mach_o import LC_LAZY_LOAD_DYLIB
from macholib.mach_o import LC_LOAD_DYLIB
from macholib.mach_o import LC_LOAD_UPWARD_DYLIB
from macholib.mach_o import LC_LOAD_WEAK_DYLIB
from macholib.mach_o import LC_REEXPORT_DYLIB
from macholib.mach_o import LC_RPATH
from macholib.mach_o import get_cpu_subtype

from . import machosign

LOG = logging.getLogger(__name__)
T = TypeVar("T")

# Maps from macholib's CPU_TYPE_NAMES entry and get_cpu_subtype output to
# what lipo would print
LIPO_ARCH_NAMES = {
    "MC680x0": {
        "CPU_SUBTYPE_MC680x0_ALL": "m68k",
        "CPU_SUBTYPE_MC68030_ONLY": "m68030",
        "CPU_SUBTYPE_MC68040": "m68040",
    },
    "PowerPC": {
        "CPU_SUBTYPE_POWERPC_ALL": "ppc",
        "CPU_SUBTYPE_POWERPC_601": "ppc601",
        "CPU_SUBTYPE_POWERPC_603": "ppc603",
        "CPU_SUBTYPE_POWERPC_603e": "ppc603e",
        "CPU_SUBTYPE_POWERPC_603ev": "ppc603ev",
        "CPU_SUBTYPE_POWERPC_604": "ppc604",
        "CPU_SUBTYPE_POWERPC_604e": "ppc604e",
        "CPU_SUBTYPE_POWERPC_750": "ppc750",
        "CPU_SUBTYPE_POWERPC_7400": "ppc7400",
        "CPU_SUBTYPE_POWERPC_7450": "ppc7450",
        "CPU_SUBTYPE_POWERPC_970": "ppc970",
    },
    "PowerPC64": {
        "CPU_SUBTYPE_POWERPC_ALL": "ppc64",
        "CPU_SUBTYPE_POWERPC_970": "ppc970-64",
    },
    "MC88000": {
        "CPU_SUBTYPE_MC88000_ALL": "m88k",
        "CPU_SUBTYPE_MC88110": "m88k",
    },
    "i386": {
        "CPU_SUBTYPE_I386_ALL": "i386",
        "CPU_SUBTYPE_486": "i486",
        "CPU_SUBTYPE_486SX": "i486SX",
        "CPU_SUBTYPE_PENT": "pentium",
        "CPU_SUBTYPE_PENTPRO": "pentpro",
        "CPU_SUBTYPE_PENTII_M3": "pentIIm3",
        "CPU_SUBTYPE_PENTII_M5": "pentIIm5",
    },
    "x86_64": {
        "CPU_SUBTYPE_X86_64_ALL": "x86_64",
        "CPU_SUBTYPE_X86_64_H": "x86_64h",
    },
    "i860": {
        "CPU_SUBTYPE_I860_ALL": "i860",
        "CPU_SUBTYPE_I860_860": "i860",
    },
    "HPPA": {
        "CPU_SUBTYPE_HPPA_7100": "hppa",
        "CPU_SUBTYPE_HPPA_7100LC": "hppa",
    },
    "SPARC": {
        "CPU_SUBTYPE_SPARC_ALL": "sparc",
    },
    "ARM": {
        "CPU_SUBTYPE_ARM_ALL": "arm",
        "CPU_SUBTYPE_ARM_V4T": "armv4t",
        "CPU_SUBTYPE_ARM_V5TEJ": "armv5",
        "CPU_SUBTYPE_ARM_XSCALE": "xscale",
        "CPU_SUBTYPE_ARM_V6": "armv6",
        "CPU_SUBTYPE_ARM_V6M": "armv6m",
        "CPU_SUBTYPE_ARM_V7": "armv7",
        "CPU_SUBTYPE_ARM_V7F": "armv7f",
        "CPU_SUBTYPE_ARM_V7S": "armv7s",
        "CPU_SUBTYPE_ARM_V7K": "armv7k",
        "CPU_SUBTYPE_ARM_V7M": "armv7m",
        "CPU_SUBTYPE_ARM_V7EM": "armv7em",
    },
    "ARM64": {
        "CPU_SUBTYPE_ARM64_ALL": "arm64",
        "CPU_SUBTYPE_ARM64_V8": "arm64v8",
        "CPU_SUBTYPE_ARM64E": "arm64e",
    },
    # TODO: macholib doesn't have this yet.
    # "ARM64_32": {
    #     "CPU_SUBTYPE_ARM64_32_V8": "arm64_32",
    # },
}


# See https://github.com/tpoechtrager/cctools-port/blob/11c93763d7e7ce7305163341d08052374e4712de/cctools/otool/ofile_print.c#L2963-L2967
# Note: I skipped LC_IDFVMLIB and LC_LOADFVMLIB - not sure if they're still used?
LIBRARY_COMMANDS = [LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LOAD_UPWARD_DYLIB, LC_LAZY_LOAD_DYLIB]


def _all_arches_same_value(macho: MachO, fn: Callable[[MachOHeader], T]) -> T:
    val = fn(macho.headers[0])
    for header in macho.headers[1:]:
        next_val = fn(header)
        if next_val != val:
            raise NotImplementedError("This function does not support separate values per-architecture")
        val = next_val

    return val


def get_install_names(filename: str) -> Tuple[str, ...]:
    """Return install names from library named in `filename`

    Returns tuple of install names

    tuple will be empty if no install names, or if this is not an object file.

    Parameters
    ----------
    filename : str
        filename of library

    Returns
    -------
    install_names : tuple
        tuple of install names for library `filename`

    Raises
    ------
    NotImplementedError
        If ``filename`` has different install names per-architecture.
    InstallNameError
        On any unexpected output from ``otool``.
    """

    # otool -L
    def _val(header: MachOHeader) -> Tuple[str]:
        results = []
        for entry in header.commands:
            lc, cmd, _ = entry
            if lc.cmd not in LIBRARY_COMMANDS:
                continue

            # cmd.name is type lc_str, whose documentation says:
            # > A long integer. A byte offset from the start of the load command that contains this
            #   string to the start of the string data
            #
            # lc_str_value takes care of getting the actual string value, and trimming trailing nulls.
            results.append(lc_str_value(cmd.name, entry).decode("utf-8"))

        return tuple(results)

    try:
        macho = MachO(filename)
        return _all_arches_same_value(macho, _val)
    except ValueError:
        return ()


def get_install_id(filename: str) -> Optional[str]:
    """Return install id from library named in `filename`

    Returns None if no install id, or if this is not an object file.

    Parameters
    ----------
    filename : str
        filename of library

    Returns
    -------
    install_id : str
        install id of library `filename`, or None if no install id

    Raises
    ------
    NotImplementedError
        If ``filename`` has different install ids per-architecture.
    """

    # otool -D
    def _val(header: MachOHeader) -> Optional[str]:
        if header.id_cmd is not None:
            entry = header.commands[header.id_cmd]
            _, cmd, _ = entry
            return lc_str_value(cmd.name, entry).decode("utf-8")

    try:
        macho = MachO(filename)
        return _all_arches_same_value(macho, _val)
    except ValueError:
        return None


def set_install_name(filename: str, oldname: str, newname: str, ad_hoc_sign: bool = True) -> None:
    """Set install name `oldname` to `newname` in library filename

    Parameters
    ----------
    filename : str
        filename of library
    oldname : str
        current install name in library
    newname : str
        replacement name for `oldname`
    ad_hoc_sign : {True, False}, optional
        If True, sign library with ad-hoc signature
    """
    # install_name_tool -change
    macho = MachO(filename)
    changed = False
    for header in macho.headers:
        for idx, entry in enumerate(header.commands):
            lc, cmd, _ = entry
            if lc.cmd not in LIBRARY_COMMANDS:
                continue

            name = lc_str_value(cmd.name, entry).decode("utf-8")
            if name == oldname:
                header.rewriteDataForCommand(idx, newname.encode("utf-8"))
                changed = True

    if changed:
        with open(filename, "r+b") as f:
            macho.write(f)

        if ad_hoc_sign:
            replace_signature(filename, "-")


def set_install_id(filename: str, install_id: str, ad_hoc_sign: bool = True):
    """Set install id for library named in `filename`

    Parameters
    ----------
    filename : str
        filename of library
    install_id : str
        install id for library `filename`
    ad_hoc_sign : {True, False}, optional
        If True, sign library with ad-hoc signature

    Raises
    ------
    RuntimeError if `filename` has not install id
    """
    # install_name_tool -id
    macho = MachO(filename)
    changed = False
    for header in macho.headers:
        if header.id_cmd is None:
            continue
        header.rewriteDataForCommand(header.id_cmd, install_id.encode("utf-8"))
        changed = True

    if changed:
        with open(filename, "r+b") as f:
            macho.write(f)

        if ad_hoc_sign:
            replace_signature(filename, "-")


def get_rpaths(filename: str) -> Tuple[str, ...]:
    """Return a tuple of rpaths from the library `filename`.

    If `filename` is not a library then the returned tuple will be empty.

    Parameters
    ----------
    filename : str
        filename of library

    Returns
    -------
    rpath : tuple
        rpath paths in `filename`

    Raises
    ------
    NotImplementedError
        If ``filename`` has different rpaths per-architecture.
    InstallNameError
        On any unexpected output from ``otool``.
    """

    # otool -l
    def _val(header: MachOHeader) -> Tuple[str]:
        results = []
        for entry in header.commands:
            lc, cmd, _ = entry
            if lc.cmd != LC_RPATH:
                continue

            # cmd.path is type lc_str.
            results.append(lc_str_value(cmd.path, entry).decode("utf-8"))

        return tuple(results)

    try:
        macho = MachO(filename)
        return _all_arches_same_value(macho, _val)
    except ValueError:
        return ()


def get_archs(filename: str) -> FrozenSet[str]:
    """Return architecture types from library `libname`

    Parameters
    ----------
    libname : str
        filename of binary for which to return arch codes

    Returns
    -------
    arch_names : frozenset
        Empty (frozen)set if no arch codes.  If not empty, contains one or more
        of 'ppc', 'ppc64', 'i386', 'x86_64', 'arm64'.
    """
    # lipo -info
    macho = MachO(filename)
    archs = set()
    for header in macho.headers:
        cputype = CPU_TYPE_NAMES.get(header.header.cputype)
        cpusubtype = get_cpu_subtype(header.header.cputype, header.header.cpusubtype)
        name = LIPO_ARCH_NAMES.get(cputype, {}).get(cpusubtype)
        if name is None:
            raise ValueError(f"Unknown cpu: type={cputype}, subtype={cpusubtype}")
        archs.add(name)
    return frozenset(archs)


def replace_signature(filename: str, identity: str) -> None:
    """Replace the signature of a binary file using `identity`

    See the codesign documentation for more info

    Parameters
    ----------
    filename : str
        Filepath to a binary file.
    identity : str
        The signing identity to use.
    """
    if identity != "-":
        raise ValueError("This implementation only supports ad-hoc signing ('-')")
    machosign.ad_hoc_sign(filename)


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
    # TODO: this function can probably be removed. The only non-test function that calls
    # it also calls `replace_signature` prior (via `set_install_id`).
    replace_signature(filename, "-")


def zip2dir(zip_fname: str, out_dir: str) -> None:
    from repairwheel._vendor.auditwheel.wheeltools import zip2dir

    return zip2dir(zip_fname, out_dir)


def dir2zip(in_dir, zip_fname):
    from repairwheel._vendor.auditwheel.wheeltools import dir2zip

    return dir2zip(in_dir, zip_fname)
