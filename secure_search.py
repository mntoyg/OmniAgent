"""Race-resistant file enumeration and reads for search_text.

All symlinks and Windows reparse points are refused, including links whose
current targets are inside the workspace. Windows support is limited to 64-bit
AMD64 on a local fixed NTFS volume; it pins directories from the volume root
without delete sharing and opens children relative to verified parent handles.
On Linux, O_PATH pins each entry so symlinks and special files can be rejected
before a read-capable open. Regular files and directories are promoted through
/proc/self/fd and checked against the pinned identity. Linux support requires
procfs and a validated ext4 workspace. Unsupported or unverifiable cases fail
closed.
"""

from __future__ import annotations

import ctypes
import ntpath
import os
import platform
import re
import stat
import struct
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from sandbox import DENIED_NAMES, DENIED_SUFFIXES, SandboxError

if TYPE_CHECKING:
    from sandbox import Workspace


_POSIX_OPEN_SUPPORTS_DIR_FD = os.open in os.supports_dir_fd
_POSIX_SCANDIR_SUPPORTS_FD = os.scandir in os.supports_fd


def _os_function(name: str) -> Callable[..., Any]:
    return cast(Callable[..., Any], getattr(os, name))


class SecureSearchError(RuntimeError):
    """Secure traversal could not verify an object and therefore stopped."""


def _ctypes_attribute(name: str) -> object:
    return cast(object, getattr(ctypes, name, None))


def _windows_library(name: str, *, use_last_error: bool = False) -> ctypes.CDLL:
    loader = _ctypes_attribute("WinDLL")
    if not callable(loader):
        raise SecureSearchError("Windows DLL loader is unavailable")
    return cast(Callable[..., ctypes.CDLL], loader)(name, use_last_error=use_last_error)


def _windows_last_error() -> int:
    getter = _ctypes_attribute("get_last_error")
    if not callable(getter):
        raise SecureSearchError("Windows last-error API is unavailable")
    return cast(Callable[[], int], getter)()


def _windows_format_error(code: int) -> str:
    formatter = _ctypes_attribute("FormatError")
    if not callable(formatter):
        raise SecureSearchError("Windows error formatter is unavailable")
    return cast(Callable[[int], str], formatter)(code)


@dataclass
class SearchHooks:
    """Deterministic race injection seam used by tests."""

    after_root_open: Callable[[Path], None] | None = None
    before_child_open: Callable[[Path], None] | None = None
    after_child_open: Callable[[Path], None] | None = None
    before_read: Callable[[Path], None] | None = None
    after_parent_verify: Callable[[str], None] | None = None
    after_posix_pin: Callable[[str, int], None] | None = None


def _lexical_candidate(workspace: Workspace, candidate: str) -> Path:
    raw = (candidate or "").strip().strip("\"'")
    if not raw or "\0" in raw or raw.startswith(("\\\\", "//")):
        raise SandboxError("invalid search path")
    supplied = Path(raw).expanduser()
    if not supplied.is_absolute():
        supplied = workspace.root / supplied
    absolute = Path(os.path.abspath(supplied))  # noqa: PTH100 - preserve lexical, non-following normalization
    try:
        relative = absolute.relative_to(workspace.root)
    except ValueError as exc:
        raise SandboxError("search path is outside the workspace") from exc
    parts: list[str] = []
    for part in relative.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise SandboxError("search path is outside the workspace")
            parts.pop()
        else:
            parts.append(part)
    return workspace.root.joinpath(*parts)


_WINDOWS_DEVICE_NAMES = frozenset(
    {"con", "prn", "aux", "nul", "conin$", "conout$", "clock$"}
    | {f"com{number}" for number in range(1, 10)}
    | {f"lpt{number}" for number in range(1, 10)}
    | {f"com{number}" for number in "¹²³"}
    | {f"lpt{number}" for number in "¹²³"}
)


def _is_windows_device_name(name: str) -> bool:
    base = name.split(":", 1)[0].rstrip(" .")
    stem = ntpath.splitext(base)[0].rstrip(" .").casefold()
    return stem in _WINDOWS_DEVICE_NAMES


def _admitted(workspace: Workspace, logical_path: Path) -> bool:
    try:
        relative = logical_path.relative_to(workspace.root)
        workspace.resolve(workspace.display(logical_path))
    except (SandboxError, OSError, ValueError):
        return False
    if any(part.startswith(".") for part in relative.parts):
        return False
    if workspace._is_denied(logical_path):  # noqa: SLF001 - preserve denied-path policy
        return False
    if logical_path.name.lower() in DENIED_NAMES:
        return False
    if os.name == "nt" and any(_is_windows_device_name(part) for part in relative.parts):
        return False
    return logical_path.suffix.lower() not in DENIED_SUFFIXES


class _Backend:
    """Small handle API shared by POSIX descriptors and Windows handles."""

    def open_root(self) -> int:
        raise NotImplementedError

    def verify_root(self, handle: int) -> None:
        raise NotImplementedError

    def verify_directory_mode(self, _handle: int) -> None:
        return None

    def enumerate(self, handle: int, max_entries: int) -> list[tuple[str, int]]:
        raise NotImplementedError

    def open_child(self, parent: int, name: str, identity: int | None) -> int:
        raise NotImplementedError

    def verify_directory_entry(
        self, parent: int, name: str, child: int, identity: int | None
    ) -> None:
        raise NotImplementedError

    def is_directory(self, handle: int) -> bool:
        raise NotImplementedError

    def is_regular_file(self, handle: int) -> bool:
        raise NotImplementedError

    def file_facts(self, handle: int) -> tuple[int, int]:
        raise NotImplementedError

    def read_bounded(self, handle: int, limit: int) -> bytes:
        raise NotImplementedError

    def close(self, handle: int) -> None:
        raise NotImplementedError


class _PosixBackend(_Backend):
    SUPPORTED_LINUX_FILESYSTEMS = frozenset({"ext4"})
    _MIN_MOUNTINFO_FIELDS = 5

    def __init__(self, workspace: Workspace, hooks: SearchHooks | None = None) -> None:
        self.workspace = workspace
        self.hooks = hooks
        self.root_identity: tuple[int, int] | None = None
        self.root_mount_id: int | None = None
        self.pinned_handles: dict[int, int] = {}

    @staticmethod
    def _unescape_mount_field(value: str) -> str:
        return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)

    @staticmethod
    def _filesystem_type(path: Path, device: int) -> str:
        major = _os_function("major")
        minor = _os_function("minor")
        expected_device = f"{major(device)}:{minor(device)}"
        matches: list[tuple[int, str]] = []
        with Path("/proc/self/mountinfo").open(encoding="ascii") as mountinfo:
            for line in mountinfo:
                fields, separator, mounted = line.rstrip("\n").partition(" - ")
                before = fields.split()
                after = mounted.split()
                if (
                    not separator
                    or len(before) < _PosixBackend._MIN_MOUNTINFO_FIELDS
                    or len(after) < 1
                    or before[2] != expected_device
                ):
                    continue
                mountpoint = Path(_PosixBackend._unescape_mount_field(before[4]))
                if path == mountpoint or path.is_relative_to(mountpoint):
                    matches.append((len(mountpoint.parts), after[0]))
        if not matches:
            raise SecureSearchError("workspace filesystem could not be identified from mountinfo")
        return max(matches, key=lambda match: match[0])[1]

    @classmethod
    def require_supported_filesystem(cls, name: str) -> None:
        if name not in cls.SUPPORTED_LINUX_FILESYSTEMS:
            raise SecureSearchError(f"unsupported Linux search filesystem: {name}")

    @staticmethod
    def _require_linux_features() -> None:
        if platform.system() != "Linux":
            raise SecureSearchError("secure POSIX search is supported on Linux only")
        if (
            not _POSIX_OPEN_SUPPORTS_DIR_FD
            or not _POSIX_SCANDIR_SUPPORTS_FD
            or not getattr(os, "O_PATH", 0)
            or not getattr(os, "O_NOFOLLOW", 0)
            or not getattr(os, "O_DIRECTORY", 0)
            or not getattr(os, "O_CLOEXEC", 0)
        ):
            raise SecureSearchError("Linux O_PATH descriptor-relative search is unavailable")

    @staticmethod
    def _verify_procfd(handle: int) -> None:
        procfd_directory = Path("/proc/self/fd")
        procfdinfo_directory = Path("/proc/self/fdinfo")
        try:
            info = procfd_directory.stat()
            fdinfo = procfdinfo_directory.stat()
        except OSError as exc:
            raise SecureSearchError("Linux procfs descriptor paths are unavailable") from exc
        if not stat.S_ISDIR(info.st_mode) or not stat.S_ISDIR(fdinfo.st_mode):
            raise SecureSearchError("Linux procfs descriptor paths are not directories")
        if (
            _PosixBackend._filesystem_type(procfd_directory, info.st_dev) != "proc"
            or _PosixBackend._filesystem_type(procfdinfo_directory, fdinfo.st_dev) != "proc"
        ):
            raise SecureSearchError("Linux descriptor paths are not on procfs")
        flags = (
            os.O_RDONLY
            | _PosixBackend._linux_flag("O_DIRECTORY")
            | _PosixBackend._linux_flag("O_CLOEXEC")
        )
        probe = os.open(f"/proc/self/fd/{handle}", flags)
        try:
            pinned = os.fstat(handle)
            opened = os.fstat(probe)
            if (opened.st_dev, opened.st_ino) != (pinned.st_dev, pinned.st_ino):
                raise SecureSearchError("procfs descriptor promotion changed object identity")
        finally:
            os.close(probe)

    @staticmethod
    def _mount_id(handle: int) -> int:
        try:
            lines = Path(f"/proc/self/fdinfo/{handle}").read_text(encoding="ascii").splitlines()
        except OSError as exc:
            raise SecureSearchError("Linux descriptor mount identity is unavailable") from exc
        values: list[int] = []
        for line in lines:
            key, separator, value = line.partition(":")
            if key != "mnt_id" or not separator:
                continue
            try:
                values.append(int(value.strip()))
            except ValueError as exc:
                raise SecureSearchError("Linux descriptor mount identity is invalid") from exc
        if len(values) != 1 or values[0] <= 0:
            raise SecureSearchError("Linux descriptor mount identity is unavailable")
        return values[0]

    @staticmethod
    def _linux_flag(name: str) -> int:
        flag = getattr(os, name, None)
        if not isinstance(flag, int):
            raise SecureSearchError(f"required Linux open flag {name} is unavailable")
        return flag

    def open_root(self) -> int:
        self._require_linux_features()
        nofollow = self._linux_flag("O_NOFOLLOW")
        directory = self._linux_flag("O_DIRECTORY")
        expected = (self.workspace._root_device, self.workspace._root_inode)  # noqa: SLF001 - verify captured root identity
        if None in expected:
            raise SecureSearchError("workspace root identity was not captured")
        fd = os.open("/", os.O_RDONLY | directory | nofollow)
        try:
            for part in self.workspace.root.parts[1:]:
                next_fd = os.open(part, os.O_RDONLY | directory | nofollow, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            info = os.fstat(fd)
            if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != expected:
                raise SecureSearchError("workspace root identity changed")  # noqa: TRY301 - close the pinned handle in the enclosing except
            self.require_supported_filesystem(
                self._filesystem_type(self.workspace.root, info.st_dev)
            )
            self.root_identity = (info.st_dev, info.st_ino)
            self.root_mount_id = self._mount_id(fd)
            self._verify_procfd(fd)
            self.verify_root(fd)
        except BaseException:
            os.close(fd)
            raise
        return fd

    def verify_root(self, handle: int) -> None:
        if self.root_identity is None:
            raise SecureSearchError("workspace root is not pinned")
        pinned = os.fstat(handle)
        try:
            current = os.lstat(self.workspace.root)
        except OSError as exc:
            raise SecureSearchError("workspace root path is no longer verifiable") from exc
        identity = (pinned.st_dev, pinned.st_ino)
        if identity != self.root_identity or stat.S_ISLNK(current.st_mode):
            raise SecureSearchError("workspace root was replaced or renamed")
        if (current.st_dev, current.st_ino) != self.root_identity:
            raise SecureSearchError("workspace root identity changed")
        if self.root_mount_id is None or self._mount_id(handle) != self.root_mount_id:
            raise SecureSearchError("workspace root mount identity changed")

    def enumerate(self, handle: int, max_entries: int) -> list[tuple[str, int]]:
        names: list[tuple[str, int]] = []
        with os.scandir(handle) as entries:
            for entry in entries:
                if entry.name in (".", ".."):
                    continue
                if len(names) >= max_entries:
                    raise SecureSearchError("workspace exceeds the search entry limit")
                names.append((entry.name, entry.inode()))
        return names

    def open_child(self, parent: int, name: str, identity: int | None) -> int:
        if not name or name in (".", "..") or "/" in name or "\0" in name:
            raise SecureSearchError("invalid Linux directory entry name")
        path_flags = (
            self._linux_flag("O_PATH")
            | self._linux_flag("O_NOFOLLOW")
            | self._linux_flag("O_CLOEXEC")
        )
        path_handle = os.open(name, path_flags, dir_fd=parent)
        io_handle: int | None = None
        try:
            pinned = os.fstat(path_handle)
            if stat.S_ISLNK(pinned.st_mode):
                raise SecureSearchError("symbolic links are not followed")  # noqa: TRY301 - close pinned fd below
            if not (stat.S_ISREG(pinned.st_mode) or stat.S_ISDIR(pinned.st_mode)):
                raise SecureSearchError("special filesystem entries are refused")  # noqa: TRY301 - close pinned fd below
            root_device = self.root_identity[0] if self.root_identity else None
            if (
                (identity not in (None, 0) and pinned.st_ino != identity)
                or pinned.st_dev != root_device
            ):
                raise SecureSearchError("entry identity or volume could not be verified")  # noqa: TRY301 - close pinned fd below
            if self.root_mount_id is None or self._mount_id(path_handle) != self.root_mount_id:
                raise SecureSearchError("entry crosses the workspace mount boundary")  # noqa: TRY301 - close pinned fd below
            if self.hooks and self.hooks.after_posix_pin:
                self.hooks.after_posix_pin(name, path_handle)
            io_flags = (
                os.O_RDONLY
                | self._linux_flag("O_CLOEXEC")
                | self._linux_flag("O_NONBLOCK")
                | self._linux_flag("O_NOCTTY")
            )
            if stat.S_ISDIR(pinned.st_mode):
                io_flags |= self._linux_flag("O_DIRECTORY")
            io_handle = os.open(f"/proc/self/fd/{path_handle}", io_flags)
            opened = os.fstat(io_handle)
            if (
                (opened.st_dev, opened.st_ino) != (pinned.st_dev, pinned.st_ino)
                or stat.S_IFMT(opened.st_mode) != stat.S_IFMT(pinned.st_mode)
            ):
                raise SecureSearchError("procfs promotion changed pinned object identity")  # noqa: TRY301 - close pinned fd below
            self.pinned_handles[io_handle] = path_handle
        except BaseException:
            if io_handle is not None:
                os.close(io_handle)
            os.close(path_handle)
            raise
        else:
            return io_handle

    def verify_directory_entry(
        self, parent: int, name: str, child: int, identity: int | None
    ) -> None:
        parent_info = os.fstat(parent)
        opened = os.fstat(child)
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (
            stat.S_ISLNK(current.st_mode)
            or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
            or (identity not in (None, 0) and opened.st_ino != identity)
            or opened.st_dev != self.root_identity[0]  # type: ignore[index]
            or parent_info.st_dev != self.root_identity[0]  # type: ignore[index]
        ):
            raise SecureSearchError("directory entry is no longer under its pinned parent")

    def is_directory(self, handle: int) -> bool:
        return stat.S_ISDIR(os.fstat(handle).st_mode)

    def is_regular_file(self, handle: int) -> bool:
        return stat.S_ISREG(os.fstat(handle).st_mode)

    def file_facts(self, handle: int) -> tuple[int, int]:
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode):
            return -1, 0
        return info.st_size, info.st_nlink

    def read_bounded(self, handle: int, limit: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < limit:
            part = os.read(handle, min(8192, limit - len(chunks)))
            if not part:
                break
            chunks.extend(part)
        return bytes(chunks)

    def close(self, handle: int) -> None:
        path_handle = self.pinned_handles.pop(handle, None)
        try:
            os.close(handle)
        finally:
            if path_handle is not None:
                os.close(path_handle)


class _WindowsBackend(_Backend):
    """Documented Win32 handle traversal, deliberately restricted to NTFS."""

    FILE_INFO_STANDARD = 1
    FILE_INFO_ATTRIBUTE_TAG = 9
    FILE_INFO_ID_BOTH = 10
    FILE_INFO_ID_BOTH_RESTART = 11
    FILE_INFO_ID = 18
    FILE_INFO_CASE_SENSITIVE = 23
    FILE_CS_FLAG_CASE_SENSITIVE_DIR = 0x00000001
    FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    FILE_SHARE_ALL = 7
    FILE_SHARE_MUTATION_LOCK = 0x00000003  # Permit reads/writes, deny rename/delete sharing.
    GENERIC_READ = 0x80000000
    FILE_READ_DATA = 0x0001
    FILE_READ_ATTRIBUTES = 0x0080
    FILE_LIST_DIRECTORY = 0x0001
    SYNCHRONIZE = 0x00100000
    FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
    FILE_OPEN_REPARSE_POINT = 0x00200000
    FILE_OPEN = 1
    OBJ_CASE_INSENSITIVE = 0x00000040
    MAX_UNICODE_STRING_BYTES = 0xFFFE
    OPEN_EXISTING = 3
    FILE_TYPE_DISK = 1
    DRIVE_FIXED = 3
    SUPPORTED_POINTER_BITS = 64
    ERROR_NO_MORE_FILES = 18

    @staticmethod
    def require_supported_architecture(machine: str, pointer_bits: int) -> None:
        if (
            machine.upper() != "AMD64"
            or pointer_bits != _WindowsBackend.SUPPORTED_POINTER_BITS
        ):
            raise SecureSearchError("unsupported Windows architecture: 64-bit AMD64 required")

    @classmethod
    def require_case_insensitive_directory(cls, flags: int) -> None:
        if flags & cls.FILE_CS_FLAG_CASE_SENSITIVE_DIR:
            raise SecureSearchError("case-sensitive Windows directories are unsupported")

    def __init__(
        self, workspace: Workspace, hooks: SearchHooks | None = None
    ) -> None:
        self.require_supported_architecture(platform.machine(), struct.calcsize("P") * 8)
        self.workspace = workspace
        self.hooks = hooks
        self.kernel32 = _windows_library("kernel32", use_last_error=True)
        self.ntdll = _windows_library("ntdll")
        self._configure()
        self.root_identity: tuple[int, int, int] | None = None
        self.root_final = ""
        self.root_handle: int | None = None
        self.root_chain: list[tuple[int, tuple[int, int, int], str]] = []

    def _configure(self) -> None:
        from ctypes import wintypes  # noqa: PLC0415 - Win32 ABI types are platform-specific

        k = self.kernel32
        k.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        k.CreateFileW.restype = wintypes.HANDLE
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        k.GetFileInformationByHandleEx.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
        ]
        k.GetFileInformationByHandleEx.restype = wintypes.BOOL
        k.SetFileInformationByHandle.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
        ]
        k.SetFileInformationByHandle.restype = wintypes.BOOL
        k.GetFileType.argtypes = [wintypes.HANDLE]
        k.GetFileType.restype = wintypes.DWORD
        k.GetFinalPathNameByHandleW.argtypes = [
            wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
        ]
        k.GetFinalPathNameByHandleW.restype = wintypes.DWORD
        k.ReadFile.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
        ]
        k.ReadFile.restype = wintypes.BOOL
        k.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
        k.GetDriveTypeW.restype = wintypes.UINT
        k.GetVolumePathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        k.GetVolumePathNameW.restype = wintypes.BOOL
        k.GetVolumeInformationW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
            wintypes.LPDWORD, wintypes.LPDWORD, wintypes.LPDWORD,
            wintypes.LPWSTR, wintypes.DWORD,
        ]
        k.GetVolumeInformationW.restype = wintypes.BOOL

        class UnicodeString(ctypes.Structure):
            _fields_ = [
                ("Length", wintypes.USHORT),
                ("MaximumLength", wintypes.USHORT),
                ("Buffer", wintypes.LPWSTR),
            ]

        class ObjectAttributes(ctypes.Structure):
            _fields_ = [
                ("Length", wintypes.ULONG),
                ("RootDirectory", wintypes.HANDLE),
                ("ObjectName", ctypes.POINTER(UnicodeString)),
                ("Attributes", wintypes.ULONG),
                ("SecurityDescriptor", wintypes.LPVOID),
                ("SecurityQualityOfService", wintypes.LPVOID),
            ]

        class IoStatusUnion(ctypes.Union):
            _fields_ = [("Status", ctypes.c_long), ("Pointer", wintypes.LPVOID)]

        class IoStatusBlock(ctypes.Structure):
            _fields_ = [("Status", IoStatusUnion), ("Information", ctypes.c_size_t)]

        ntdll = self.ntdll
        ntdll.NtCreateFile.argtypes = [
            ctypes.POINTER(wintypes.HANDLE),
            wintypes.DWORD,
            ctypes.POINTER(ObjectAttributes),
            ctypes.POINTER(IoStatusBlock),
            ctypes.POINTER(ctypes.c_longlong),
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        ntdll.NtCreateFile.restype = ctypes.c_long
        ntdll.RtlNtStatusToDosError.argtypes = [ctypes.c_long]
        ntdll.RtlNtStatusToDosError.restype = wintypes.ULONG
        self._UnicodeString = UnicodeString
        self._ObjectAttributes = ObjectAttributes
        self._IoStatusBlock = IoStatusBlock

    def _open_relative(self, parent: int, name: str) -> int:
        """Open one enumerated component relative to its already-verified handle."""
        from ctypes import wintypes  # noqa: PLC0415 - Win32 ABI types are platform-specific

        if (
            not name
            or name in (".", "..")
            or any(character in name for character in ("\0", "\\", "/", ":"))
        ):
            raise SecureSearchError("invalid Windows directory entry name")
        encoded = name.encode("utf-16-le", errors="strict")
        if len(encoded) > self.MAX_UNICODE_STRING_BYTES:
            raise SecureSearchError("Windows directory entry name is too long")
        name_buffer = ctypes.create_unicode_buffer(name)
        unicode_name = self._UnicodeString(
            len(encoded),
            len(encoded) + ctypes.sizeof(ctypes.c_wchar),
            ctypes.cast(name_buffer, wintypes.LPWSTR),
        )
        attributes = self._ObjectAttributes(
            ctypes.sizeof(self._ObjectAttributes),
            wintypes.HANDLE(parent),
            ctypes.pointer(unicode_name),
            self.OBJ_CASE_INSENSITIVE,
            None,
            None,
        )
        io_status = self._IoStatusBlock()
        handle = wintypes.HANDLE()
        desired_access = (
            self.FILE_READ_DATA
            | self.FILE_READ_ATTRIBUTES
            | self.FILE_LIST_DIRECTORY
            | self.SYNCHRONIZE
        )
        create_options = self.FILE_OPEN_REPARSE_POINT | self.FILE_SYNCHRONOUS_IO_NONALERT
        status = self.ntdll.NtCreateFile(
            ctypes.byref(handle),
            desired_access,
            ctypes.byref(attributes),
            ctypes.byref(io_status),
            None,
            0,
            self.FILE_SHARE_MUTATION_LOCK,
            self.FILE_OPEN,
            create_options,
            None,
            0,
        )
        if status < 0:
            code = int(self.ntdll.RtlNtStatusToDosError(status))
            detail = _windows_format_error(code).strip()
            raise OSError(code, f"NtCreateFile(relative child {name!r}): {detail}")
        if handle.value is None:
            raise SecureSearchError("NtCreateFile returned no child handle")
        return int(handle.value)

    def _error(self, operation: str) -> OSError:
        code = _windows_last_error()
        return OSError(code, f"{operation}: {_windows_format_error(code).strip()}")

    def _query(
        self, handle: int, info_class: int, structure: type[ctypes.Structure]
    ) -> ctypes.Structure:
        value = structure()
        ok = self.kernel32.GetFileInformationByHandleEx(
            handle, info_class, ctypes.byref(value), ctypes.sizeof(value)
        )
        if not ok:
            raise self._error(f"GetFileInformationByHandleEx({info_class})")
        return value

    def _identity(self, handle: int) -> tuple[int, int, int]:
        class FileIdInfo(ctypes.Structure):
            _fields_ = [("VolumeSerialNumber", ctypes.c_uint64), ("FileId", ctypes.c_ubyte * 16)]
        info = self._query(handle, self.FILE_INFO_ID, FileIdInfo)
        volume = int(info.VolumeSerialNumber)
        file_id = bytes(info.FileId)
        return (
            volume,
            int.from_bytes(file_id[:8], "little", signed=False),
            int.from_bytes(file_id[8:], "little", signed=False),
        )

    def _attributes(self, handle: int) -> tuple[int, int]:
        from ctypes import wintypes  # noqa: PLC0415 - Win32 ABI types are platform-specific

        class FileAttributeTagInfo(ctypes.Structure):
            _fields_ = [("FileAttributes", wintypes.DWORD), ("ReparseTag", wintypes.DWORD)]
        info = self._query(handle, self.FILE_INFO_ATTRIBUTE_TAG, FileAttributeTagInfo)
        return int(info.FileAttributes), int(info.ReparseTag)

    def _standard(self, handle: int) -> tuple[int, int, bool]:
        from ctypes import wintypes  # noqa: PLC0415 - Win32 ABI types are platform-specific

        class FileStandardInfo(ctypes.Structure):
            _fields_ = [
                ("AllocationSize", ctypes.c_int64),
                ("EndOfFile", ctypes.c_int64),
                ("NumberOfLinks", wintypes.DWORD),
                ("DeletePending", ctypes.c_ubyte),
                ("Directory", ctypes.c_ubyte),
            ]
        info = self._query(handle, self.FILE_INFO_STANDARD, FileStandardInfo)
        return int(info.EndOfFile), int(info.NumberOfLinks), bool(info.Directory)

    def _final_path(self, handle: int) -> str:
        needed = self.kernel32.GetFinalPathNameByHandleW(handle, None, 0, 0)
        if needed == 0:
            raise self._error("GetFinalPathNameByHandleW(size)")
        buffer = ctypes.create_unicode_buffer(needed + 1)
        written = self.kernel32.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
        if written == 0 or written >= len(buffer):
            raise self._error("GetFinalPathNameByHandleW(path)")
        return buffer.value

    @staticmethod
    def _path_parts(path: str) -> tuple[str, tuple[str, ...]]:
        normalized = ntpath.normpath(path)
        if normalized.startswith("\\\\?\\UNC\\"):
            normalized = "\\\\" + normalized[8:]
        elif normalized.startswith("\\\\?\\"):
            normalized = normalized[4:]
        drive, tail = ntpath.splitdrive(normalized)
        return drive.casefold(), tuple(part for part in tail.split("\\") if part)

    @classmethod
    def path_is_within(cls, root: str, child: str) -> bool:
        root_drive, root_parts = cls._path_parts(root)
        child_drive, child_parts = cls._path_parts(child)
        return (
            root_drive == child_drive
            and len(child_parts) >= len(root_parts)
            and child_parts[: len(root_parts)] == root_parts
        )

    def _verify_contained(self, handle: int) -> str:
        if self.root_identity is None:
            raise SecureSearchError("workspace root identity is not pinned")
        identity = self._identity(handle)
        if identity[0] != self.root_identity[0]:
            raise SecureSearchError("entry is on an unsupported volume")
        final = self._final_path(handle)
        if not self.path_is_within(self.root_final, final):
            raise SecureSearchError("final handle path is outside or case-ambiguous")
        return final

    def _open_directory_handle(self, path: str) -> int:
        handle = self.kernel32.CreateFileW(
            path,
            self.GENERIC_READ | self.FILE_READ_ATTRIBUTES | self.FILE_LIST_DIRECTORY,
            self.FILE_SHARE_MUTATION_LOCK,
            None,
            self.OPEN_EXISTING,
            self.FILE_FLAG_BACKUP_SEMANTICS | self.FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        if handle == ctypes.c_void_p(-1).value:
            raise self._error(f"CreateFileW(directory {path!r})")
        return int(handle)

    @classmethod
    def _same_path_case_sensitive(cls, expected: str, actual: str) -> bool:
        return cls._path_parts(expected) == cls._path_parts(actual)

    def open_root(self) -> int:
        drive, tail = ntpath.splitdrive(str(self.workspace.root))
        if not drive:
            raise SecureSearchError("workspace root has no verifiable Windows volume")
        volume_root = drive.rstrip("\\") + "\\"
        components = [part for part in tail.split("\\") if part]
        expected_path = volume_root
        handles: list[int] = []
        try:
            for component in [None, *components]:
                if component is not None:
                    expected_path = ntpath.join(expected_path, component)
                handle = self._open_directory_handle(expected_path)
                handles.append(handle)
                attrs, _ = self._attributes(handle)
                _, _, is_dir = self._standard(handle)
                if attrs & self.FILE_ATTRIBUTE_REPARSE_POINT or not is_dir:
                    raise SecureSearchError("workspace ancestor is not an ordinary directory")  # noqa: TRY301 - close pinned handles in the enclosing except
                identity = self._identity(handle)
                if identity[2] != 0:
                    raise SecureSearchError("NTFS directory has a nonzero upper 64-bit file ID")  # noqa: TRY301 - close pinned handles in the enclosing except
                final = self._final_path(handle)
                if not self._same_path_case_sensitive(expected_path, final):
                    raise SecureSearchError("workspace ancestor final path is case-ambiguous")  # noqa: TRY301 - close pinned handles in the enclosing except
                if handles and identity[0] != self._identity(handles[0])[0]:
                    raise SecureSearchError("workspace path crosses a Windows volume")  # noqa: TRY301 - close pinned handles in the enclosing except
                self.root_chain.append((handle, identity, final))
            root_handle, self.root_identity, self.root_final = self.root_chain[-1]
            expected = (self.workspace._root_device, self.workspace._root_inode)  # noqa: SLF001 - verify captured root identity
            if None in expected or self.root_identity != (expected[0], expected[1], 0):
                raise SecureSearchError("workspace root identity changed before pinning")  # noqa: TRY301 - close pinned handles in the enclosing except
            self.root_handle = root_handle
            self._verify_ntfs(self.root_final)
            self.verify_directory_mode(root_handle)
            self.verify_root(root_handle)
        except BaseException:
            for handle in reversed(handles):
                self.kernel32.CloseHandle(handle)
            self.root_chain.clear()
            self.root_handle = None
            self.root_identity = None
            raise
        else:
            return root_handle

    def _verify_ntfs(self, root_final: str) -> None:
        from ctypes import wintypes  # noqa: PLC0415 - Win32 ABI types are platform-specific

        volume_path = ctypes.create_unicode_buffer(32768)
        if not self.kernel32.GetVolumePathNameW(root_final, volume_path, len(volume_path)):
            raise self._error("GetVolumePathNameW")
        fs_name = ctypes.create_unicode_buffer(64)
        serial = wintypes.DWORD()
        max_component = wintypes.DWORD()
        flags = wintypes.DWORD()
        if not self.kernel32.GetVolumeInformationW(
            volume_path.value, None, 0, ctypes.byref(serial), ctypes.byref(max_component),
            ctypes.byref(flags), fs_name, len(fs_name),
        ):
            raise self._error("GetVolumeInformationW")
        self.require_local_fixed_drive(int(self.kernel32.GetDriveTypeW(volume_path.value)))
        self.require_supported_filesystem(fs_name.value)

    @classmethod
    def require_local_fixed_drive(cls, drive_type: int) -> None:
        if drive_type != cls.DRIVE_FIXED:
            raise SecureSearchError("unsupported Windows drive type: local fixed volume required")

    @staticmethod
    def require_supported_filesystem(name: str) -> None:
        if name.upper() != "NTFS":
            raise SecureSearchError(f"unsupported Windows filesystem: {name}")

    def verify_directory_mode(self, handle: int) -> None:
        from ctypes import wintypes  # noqa: PLC0415 - Win32 ABI types are platform-specific

        class FileCaseSensitiveInfo(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD)]

        info = self._query(handle, self.FILE_INFO_CASE_SENSITIVE, FileCaseSensitiveInfo)
        self.require_case_insensitive_directory(int(info.Flags))

    def verify_root(self, handle: int) -> None:
        if (
            self.root_identity is None
            or self.root_handle != handle
            or self._identity(handle) != self.root_identity
        ):
            raise SecureSearchError("pinned workspace root identity changed")
        for pinned_handle, identity, final_path in self.root_chain:
            if self._identity(pinned_handle) != identity:
                raise SecureSearchError("pinned workspace ancestor identity changed")
            if self._final_path(pinned_handle) != final_path:
                raise SecureSearchError("workspace ancestor was renamed or replaced")

    def enumerate(self, handle: int, max_entries: int) -> list[tuple[str, int]]:
        from ctypes import wintypes  # noqa: PLC0415 - Win32 ABI types are platform-specific

        class FileIdBothDirInfo(ctypes.Structure):
            _fields_ = [
                ("NextEntryOffset", wintypes.DWORD),
                ("FileIndex", wintypes.DWORD),
                ("CreationTime", ctypes.c_int64),
                ("LastAccessTime", ctypes.c_int64),
                ("LastWriteTime", ctypes.c_int64),
                ("ChangeTime", ctypes.c_int64),
                ("EndOfFile", ctypes.c_int64),
                ("AllocationSize", ctypes.c_int64),
                ("FileAttributes", wintypes.DWORD),
                ("FileNameLength", wintypes.DWORD),
                ("EaSize", wintypes.DWORD),
                ("ShortNameLength", ctypes.c_ubyte),
                ("ShortName", wintypes.WCHAR * 12),
                ("FileId", ctypes.c_int64),
                ("FileName", wintypes.WCHAR * 1),
            ]
        names: list[tuple[str, int]] = []
        info_class = self.FILE_INFO_ID_BOTH_RESTART
        while True:
            buffer = ctypes.create_string_buffer(64 * 1024)
            ok = self.kernel32.GetFileInformationByHandleEx(handle, info_class, buffer, len(buffer))
            info_class = self.FILE_INFO_ID_BOTH
            if not ok:
                code = _windows_last_error()
                if code == self.ERROR_NO_MORE_FILES:
                    break
                raise self._error("GetFileInformationByHandleEx(directory)")
            offset = 0
            while True:
                entry = ctypes.cast(
                    ctypes.byref(buffer, offset), ctypes.POINTER(FileIdBothDirInfo)
                ).contents
                count = int(entry.FileNameLength)
                if count % 2:
                    raise SecureSearchError("directory entry has invalid UTF-16 name length")
                name_start = ctypes.addressof(entry) + FileIdBothDirInfo.FileName.offset
                name = ctypes.string_at(name_start, count).decode("utf-16-le", errors="strict")
                signed_file_id = int(entry.FileId)
                file_id = signed_file_id & 0xFFFFFFFFFFFFFFFF
                if name not in (".", ".."):
                    if len(names) >= max_entries:
                        raise SecureSearchError("workspace exceeds the search entry limit")
                    if file_id == 0:
                        raise SecureSearchError("filesystem did not provide a verifiable file ID")
                    names.append((name, file_id))
                next_offset = int(entry.NextEntryOffset)
                if next_offset == 0:
                    break
                if next_offset < FileIdBothDirInfo.FileName.offset + count:
                    raise SecureSearchError(
                        "directory enumeration returned an invalid entry offset"
                    )
                offset += next_offset
        return names

    def open_child(self, parent: int, name: str, identity: int | None) -> int:
        self._verify_contained(parent)
        if self.hooks and self.hooks.after_parent_verify:
            self.hooks.after_parent_verify(name)
        value = self._open_relative(parent, name)
        try:
            attrs, _ = self._attributes(value)
            if attrs & self.FILE_ATTRIBUTE_REPARSE_POINT:
                raise SecureSearchError("all reparse points are refused")  # noqa: TRY301 - close the pinned handle in the enclosing except
            opened_identity = self._identity(value)
            if opened_identity[2] != 0:
                raise SecureSearchError("NTFS entry has a nonzero upper 64-bit file ID")  # noqa: TRY301 - close the pinned handle in the enclosing except
            if identity not in (None, 0) and opened_identity[1] != identity:
                raise SecureSearchError("enumerated and opened NTFS file IDs differ")  # noqa: TRY301 - close the pinned handle in the enclosing except
            if self.root_identity is None or opened_identity[0] != self.root_identity[0]:
                raise SecureSearchError("entry is on an unsupported volume")  # noqa: TRY301 - close the pinned handle in the enclosing except
            self._verify_contained(value)
        except BaseException:
            self.close(value)
            raise
        return value

    def verify_directory_entry(
        self, parent: int, name: str, child: int, identity: int | None
    ) -> None:
        parent_final = self._verify_contained(parent)
        child_final = self._verify_contained(child)
        parent_drive, parent_parts = self._path_parts(parent_final)
        child_drive, child_parts = self._path_parts(child_final)
        if (
            parent_drive != child_drive
            or child_parts[:-1] != parent_parts
            or not child_parts
            or child_parts[-1] != name
        ):
            raise SecureSearchError(
                "directory handle no longer matches its enumerated parent entry"
            )
        opened_identity = self._identity(child)
        if opened_identity[2] != 0:
            raise SecureSearchError("NTFS entry has a nonzero upper 64-bit file ID")
        if identity not in (None, 0) and opened_identity[1] != identity:
            raise SecureSearchError("enumerated and opened NTFS file IDs differ")

    def is_directory(self, handle: int) -> bool:
        attrs, _ = self._attributes(handle)
        if attrs & self.FILE_ATTRIBUTE_REPARSE_POINT:
            raise SecureSearchError("all reparse points are refused")
        _, _, is_dir = self._standard(handle)
        if self.kernel32.GetFileType(handle) != self.FILE_TYPE_DISK:
            raise SecureSearchError("non-disk object refused")
        return is_dir

    def is_regular_file(self, handle: int) -> bool:
        attrs, _ = self._attributes(handle)
        if attrs & self.FILE_ATTRIBUTE_REPARSE_POINT:
            raise SecureSearchError("all reparse points are refused")
        _, _, is_dir = self._standard(handle)
        if self.kernel32.GetFileType(handle) != self.FILE_TYPE_DISK:
            raise SecureSearchError("non-disk object refused")
        return not is_dir

    def file_facts(self, handle: int) -> tuple[int, int]:
        attrs, _ = self._attributes(handle)
        if attrs & self.FILE_ATTRIBUTE_REPARSE_POINT:
            raise SecureSearchError("all reparse points are refused")
        self._verify_contained(handle)
        size, links, is_dir = self._standard(handle)
        if is_dir or self.kernel32.GetFileType(handle) != self.FILE_TYPE_DISK:
            return -1, links
        return size, links

    def read_bounded(self, handle: int, limit: int) -> bytes:
        from ctypes import wintypes  # noqa: PLC0415 - Win32 ABI types are platform-specific

        chunks = bytearray()
        while len(chunks) < limit:
            request = min(8192, limit - len(chunks))
            buffer = ctypes.create_string_buffer(request)
            count = wintypes.DWORD()
            ok = self.kernel32.ReadFile(handle, buffer, request, ctypes.byref(count), None)
            if not ok:
                raise self._error("ReadFile(verified handle)")
            if count.value == 0:
                break
            chunks.extend(buffer.raw[: count.value])
        return bytes(chunks)

    def close(self, handle: int) -> None:
        if handle == self.root_handle:
            handles = [entry[0] for entry in self.root_chain]
            self.root_chain.clear()
            self.root_handle = None
            self.root_identity = None
            for pinned_handle in reversed(handles):
                if not self.kernel32.CloseHandle(pinned_handle):
                    raise self._error("CloseHandle(workspace ancestor)")
            return
        if not self.kernel32.CloseHandle(handle):
            raise self._error("CloseHandle")


def _read_file(  # noqa: PLR0913, PLR0917 - explicit handles and ancestry inputs aid auditing
    workspace: Workspace,
    backend: _Backend,
    root_handle: int,
    file_handle: int,
    logical_path: Path,
    hooks: SearchHooks | None,
) -> bytes | None:
    if not backend.is_regular_file(file_handle):
        return None
    size, link_count = backend.file_facts(file_handle)
    if size < 0 or size > workspace.max_file_bytes or link_count > 1:
        return None
    backend.verify_root(root_handle)
    if hooks and hooks.before_read:
        hooks.before_read(logical_path)
    blob = backend.read_bounded(file_handle, workspace.max_file_bytes + 1)
    backend.verify_root(root_handle)
    if len(blob) > workspace.max_file_bytes:
        return None
    return blob


DirectoryLink = tuple[int, str, int, int | None]
MAX_SECURE_SEARCH_DEPTH = 256
MAX_SEARCH_ENTRIES = 100_000  # A traversal-wide budget bounds retained sorted entries.


@dataclass
class TraversalBudget:
    max_files: int | None
    files_scanned: int = 0
    entries_remaining: int = MAX_SEARCH_ENTRIES


def _verify_chain(
    backend: _Backend,
    root_handle: int,
    ancestry: tuple[DirectoryLink, ...],
) -> None:
    backend.verify_root(root_handle)
    for parent, name, child, identity in ancestry:
        backend.verify_directory_entry(parent, name, child, identity)
    backend.verify_root(root_handle)


def _walk(  # noqa: PLR0913, PLR0917 - explicit handles and ancestry inputs aid auditing
    workspace: Workspace,
    backend: _Backend,
    root_handle: int,
    directory_handle: int,
    logical_directory: Path,
    ancestry: tuple[DirectoryLink, ...],
    hooks: SearchHooks | None,
    budget: TraversalBudget,
) -> Iterator[tuple[Path, bytes]]:
    if len(ancestry) > MAX_SECURE_SEARCH_DEPTH:
        raise SecureSearchError("workspace path exceeds the secure traversal depth limit")
    if budget.max_files is not None and budget.files_scanned >= budget.max_files:
        return
    _verify_chain(backend, root_handle, ancestry)
    backend.verify_directory_mode(directory_handle)
    entries = backend.enumerate(directory_handle, budget.entries_remaining)
    budget.entries_remaining -= len(entries)
    _verify_chain(backend, root_handle, ancestry)
    for name, identity in sorted(entries, key=lambda entry: entry[0]):
        if budget.max_files is not None and budget.files_scanned >= budget.max_files:
            return
        child_path = logical_directory / name
        if not _admitted(workspace, child_path):
            continue
        _verify_chain(backend, root_handle, ancestry)
        if hooks and hooks.before_child_open:
            hooks.before_child_open(child_path)
        try:
            child = backend.open_child(directory_handle, name, identity)
        except (OSError, SecureSearchError):
            continue
        try:
            if hooks and hooks.after_child_open:
                hooks.after_child_open(child_path)
            _verify_chain(backend, root_handle, ancestry)
            backend.verify_directory_entry(directory_handle, name, child, identity)
            if backend.is_directory(child):
                link = (directory_handle, name, child, identity)
                yield from _walk(
                    workspace,
                    backend,
                    root_handle,
                    child,
                    child_path,
                    (*ancestry, link),
                    hooks,
                    budget,
                )
            elif backend.is_regular_file(child):
                blob = _read_file(workspace, backend, root_handle, child, child_path, hooks)
                if blob is not None:
                    budget.files_scanned += 1
                    yield child_path, blob
        finally:
            backend.close(child)


def _iter_search_files(  # noqa: PLR0912 - guards remain adjacent to each lifecycle step
    workspace: Workspace,
    candidate: str,
    hooks: SearchHooks | None,
    max_files: int | None,
) -> Iterator[tuple[Path, bytes]]:
    start = workspace.resolve(candidate or ".")
    logical_start = _lexical_candidate(workspace, candidate or ".")
    if not _admitted(workspace, logical_start):
        raise SecureSearchError("search path is not admitted")
    relative_parts = logical_start.relative_to(workspace.root).parts
    if len(relative_parts) > MAX_SECURE_SEARCH_DEPTH:
        raise SecureSearchError("workspace path exceeds the secure traversal depth limit")
    backend: _Backend = (
        _WindowsBackend(workspace, hooks)
        if os.name == "nt"
        else _PosixBackend(workspace, hooks)
    )
    root_handle = backend.open_root()
    handles = [root_handle]
    current = root_handle
    ancestry: tuple[DirectoryLink, ...] = ()
    budget = TraversalBudget(
        max_files=max_files, entries_remaining=MAX_SEARCH_ENTRIES
    )
    try:
        if hooks and hooks.after_root_open:
            hooks.after_root_open(workspace.root)
        backend.verify_root(root_handle)
        current_logical = workspace.root
        for part in relative_parts:
            _verify_chain(backend, root_handle, ancestry)
            next_logical = current_logical / part
            if not _admitted(workspace, next_logical):
                raise SecureSearchError("search path contains a refused component")
            if hooks and hooks.before_child_open:
                hooks.before_child_open(next_logical)
            parent = current
            child = backend.open_child(parent, part, None)
            handles.append(child)
            if hooks and hooks.after_child_open:
                hooks.after_child_open(next_logical)
            backend.verify_directory_entry(parent, part, child, None)
            ancestry += ((parent, part, child, None),)
            _verify_chain(backend, root_handle, ancestry)
            current = child
            current_logical = next_logical
        if backend.is_directory(current):
            yield from _walk(
                workspace,
                backend,
                root_handle,
                current,
                logical_start,
                ancestry,
                hooks,
                budget,
            )
        else:
            _verify_chain(backend, root_handle, ancestry[:-1])
            if ancestry:
                parent, name, child, identity = ancestry[-1]
                backend.verify_directory_entry(parent, name, child, identity)
            if max_files != 0:
                blob = _read_file(workspace, backend, root_handle, current, logical_start, hooks)
                if blob is not None:
                    budget.files_scanned += 1
                    yield start, blob
    finally:
        for handle in reversed(handles):
            backend.close(handle)


def iter_search_files(
    workspace: Workspace,
    candidate: str,
    *,
    hooks: SearchHooks | None = None,
    max_files: int | None = None,
) -> Iterator[tuple[Path, bytes]]:
    """Yield admitted file bytes read through the verified open object."""
    try:
        yield from _iter_search_files(workspace, candidate, hooks, max_files)
    except SecureSearchError:
        raise
    except (OSError, UnicodeError) as exc:
        raise SecureSearchError(f"secure traversal failed closed: {exc}") from exc
