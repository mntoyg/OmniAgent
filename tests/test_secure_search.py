"""Race and policy regressions for secure search traversal."""

from __future__ import annotations

import ctypes
import os
import queue
import subprocess
import threading
from pathlib import Path

import pytest

import secure_search
import tools
from sandbox import Workspace
from secure_search import (
    SearchHooks,
    SecureSearchError,
    _is_windows_device_name,
    _WindowsBackend,
)
from tools import search_text

OUTSIDE = "OUTSIDE_MARKER_9f7c"


def _install(monkeypatch: pytest.MonkeyPatch, workspace: Workspace) -> None:
    monkeypatch.setattr(tools, "get_workspace", lambda: workspace)


def _directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        command = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
        result = subprocess.run(  # noqa: S603 - fixed cmd.exe verb and test-owned temporary paths
            [command, "/d", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            pytest.skip(
                "BLOCKED: Windows junction creation unavailable: "
                f"{result.stdout.strip()} {result.stderr.strip()}"
            )
    else:
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"BLOCKED: POSIX directory symlink creation unavailable: {exc}")


def _file_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"BLOCKED: file symlink creation unavailable: {exc}")


def _outside_marker(tmp_path: Path) -> tuple[Path, Path]:
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "secret.txt"
    marker.write_text(OUTSIDE, encoding="utf-8")
    return outside, marker


def test_directory_replaced_by_external_junction_or_symlink_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    ordinary = root / "swapdir"
    ordinary.mkdir()
    (ordinary / "ordinary.txt").write_text("ordinary", encoding="utf-8")
    outside, _ = _outside_marker(tmp_path)
    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)
    changed = False

    def replace(path: Path) -> None:
        nonlocal changed
        if path == ordinary and not changed:
            try:
                ordinary.rename(root / "ordinary-saved")
            except OSError:
                if os.name != "nt":
                    raise
                pytest.skip("BLOCKED: Windows directory rename for junction mutation unavailable")
            changed = True
            _directory_link(ordinary, outside)

    observed_reparse_point = False
    if os.name == "nt":
        original_attributes = _WindowsBackend._attributes

        def record_reparse(
            backend: _WindowsBackend, handle: int
        ) -> tuple[int, int]:
            nonlocal observed_reparse_point
            result = original_attributes(backend, handle)
            if result[0] & backend.FILE_ATTRIBUTE_REPARSE_POINT:
                observed_reparse_point = True
            return result

        monkeypatch.setattr(_WindowsBackend, "_attributes", record_reparse)
    result = search_text(OUTSIDE, _hooks=SearchHooks(before_child_open=replace))
    if os.name == "nt":
        assert changed, "the Windows junction mutation must occur before the child open"
        assert observed_reparse_point, "the Windows junction must hit the reparse-point guard"
    else:
        assert changed
    assert "1 match" not in result


def test_ancestor_replaced_after_open_is_not_enumerated_as_external(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    ancestor = root / "ancestor"
    ancestor.mkdir()
    (ancestor / "ordinary.txt").write_text("ordinary", encoding="utf-8")
    outside, _ = _outside_marker(tmp_path)
    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)
    changed = False
    mutation_blocked = False

    def replace(path: Path) -> None:
        nonlocal changed, mutation_blocked
        if path == ancestor and not changed and not mutation_blocked:
            try:
                ancestor.rename(root / "ancestor-saved")
            except OSError:
                if os.name != "nt":
                    raise
                mutation_blocked = True
                return
            changed = True
            _directory_link(ancestor, outside)

    result = search_text(OUTSIDE, _hooks=SearchHooks(after_child_open=replace))
    assert changed or (os.name == "nt" and mutation_blocked)
    assert "1 match" not in result


@pytest.mark.skipif(os.name != "nt", reason="BLOCKED: Windows handle-relative open test")
def test_windows_parent_handle_denies_ancestor_swap_before_child_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    ancestor = root / "ancestor"
    ancestor.mkdir()
    (ancestor / "secret.txt").write_text("ordinary", encoding="utf-8")
    outside, _ = _outside_marker(tmp_path)
    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)
    changed = False
    mutation_blocked = False
    hook_names: list[str] = []
    rename_errors: list[str] = []

    def replace(name: str) -> None:
        nonlocal changed, mutation_blocked
        hook_names.append(name)
        if name != "secret.txt" or changed:
            return
        try:
            ancestor.rename(root / "ancestor-saved")
        except OSError as exc:
            rename_errors.append(str(exc))
            mutation_blocked = True
            return
        changed = True
        _directory_link(ancestor, outside)

    read_paths: list[Path] = []
    result = search_text(
        OUTSIDE,
        _hooks=SearchHooks(after_parent_verify=replace, before_read=read_paths.append),
    )
    assert "secret.txt" in hook_names
    assert changed or mutation_blocked, (
        f"the ancestor move must either be blocked or exercise the replacement path; "
        f"names={hook_names}, rename_errors={rename_errors}, result={result}"
    )
    if changed:
        assert read_paths == [], "the changed ancestor chain must be rejected before reading"
    assert "1 match" not in result


@pytest.mark.skipif(os.name != "nt", reason="BLOCKED: Windows NtCreateFile relative-open test")
def test_windows_relative_open_stays_on_parent_handle_after_path_replacement(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    ancestor = root / "ancestor"
    ancestor.mkdir()
    (ancestor / "secret.txt").write_text("INTERNAL_ONLY", encoding="utf-8")
    outside, outside_file = _outside_marker(tmp_path)
    (outside / "secret.txt").write_text(OUTSIDE, encoding="utf-8")
    probe = _WindowsBackend(Workspace.at(root))
    parent_handle = probe.kernel32.CreateFileW(
        str(ancestor),
        probe.FILE_LIST_DIRECTORY | probe.FILE_READ_ATTRIBUTES,
        probe.FILE_SHARE_ALL,
        None,
        probe.OPEN_EXISTING,
        probe.FILE_FLAG_BACKUP_SEMANTICS | probe.FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if parent_handle == ctypes.c_void_p(-1).value:
        pytest.skip("BLOCKED: could not pin parent directory for the relative-open race")

    child_handle: int | None = None
    try:
        ancestor.rename(root / "ancestor-saved")
        _directory_link(ancestor, outside)
        child_handle = probe._open_relative(int(parent_handle), "secret.txt")
        final_path = probe._final_path(child_handle)
        assert "ancestor-saved\\secret.txt" in final_path
        assert str(outside_file) not in final_path
        assert probe.read_bounded(child_handle, 1024) == b"INTERNAL_ONLY"
    finally:
        if child_handle is not None:
            probe.close(child_handle)
        probe.close(int(parent_handle))


def test_file_replaced_by_external_symlink_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    victim = root / "victim.txt"
    victim.write_text("ordinary", encoding="utf-8")
    _, outside_file = _outside_marker(tmp_path)
    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)
    changed = False

    def replace(path: Path) -> None:
        nonlocal changed
        if path == victim and not changed:
            changed = True
            victim.rename(root / "victim-saved.txt")
            _file_link(victim, outside_file)

    result = search_text(OUTSIDE, _hooks=SearchHooks(before_child_open=replace))
    assert changed
    assert "1 match" not in result


def test_file_replaced_after_open_is_read_from_verified_handle_or_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    victim = root / "victim.txt"
    victim.write_text("INTERNAL_ONLY", encoding="utf-8")
    _, outside_file = _outside_marker(tmp_path)
    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)
    changed = False
    mutation_blocked = False

    def replace(path: Path) -> None:
        nonlocal changed, mutation_blocked
        if path == victim and not changed and not mutation_blocked:
            try:
                victim.rename(root / "victim-saved.txt")
            except OSError:
                if os.name != "nt":
                    raise
                mutation_blocked = True
                return
            changed = True
            _file_link(victim, outside_file)

    result = search_text(OUTSIDE, _hooks=SearchHooks(after_child_open=replace))
    assert changed or (os.name == "nt" and mutation_blocked)
    assert "1 match" not in result


def test_root_replacement_after_pin_aborts_without_reopening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "ordinary.txt").write_text("ordinary", encoding="utf-8")
    outside, _ = _outside_marker(tmp_path)
    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)
    changed = False
    mutation_blocked = False

    def replace(path: Path) -> None:
        nonlocal changed, mutation_blocked
        if path == root and not changed and not mutation_blocked:
            try:
                root.rename(tmp_path / "workspace-saved")
            except OSError:
                if os.name != "nt":
                    raise
                mutation_blocked = True
                return
            changed = True
            _directory_link(root, outside)

    result = search_text(OUTSIDE, _hooks=SearchHooks(after_root_open=replace))
    assert changed or (os.name == "nt" and mutation_blocked)
    if changed:
        assert result.startswith("Error: search stopped safely:")
    assert "1 match" not in result


def test_root_replacement_before_open_fails_identity_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    workspace = Workspace.at(root)
    old = tmp_path / "workspace-saved"
    root.rename(old)
    root.mkdir()
    (root / "secret.txt").write_text(OUTSIDE, encoding="utf-8")
    _install(monkeypatch, workspace)

    result = search_text(OUTSIDE)
    assert result.startswith("Error: search stopped safely:")
    assert "1 match" not in result


def test_missing_entry_between_enumerate_and_open_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    victim = root / "victim.txt"
    victim.write_text(OUTSIDE, encoding="utf-8")
    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)
    changed = False

    def remove(path: Path) -> None:
        nonlocal changed
        if path == victim and not changed:
            changed = True
            victim.unlink()

    result = search_text(OUTSIDE, _hooks=SearchHooks(before_child_open=remove))
    assert changed
    assert "1 match" not in result


def test_file_growth_after_size_check_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    victim = root / "victim.txt"
    victim.write_bytes(b"NEEDLE")
    workspace = Workspace.at(root, max_file_bytes=32)
    _install(monkeypatch, workspace)
    changed = False

    def grow(path: Path) -> None:
        nonlocal changed
        if path == victim and not changed:
            changed = True
            victim.write_bytes(b"NEEDLE" + b"x" * 128)

    result = search_text("NEEDLE", _hooks=SearchHooks(before_read=grow))
    assert changed
    assert "1 match" not in result


def test_hidden_credential_and_denied_entries_remain_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    hidden = root / ".hidden"
    hidden.mkdir()
    (hidden / "hidden.txt").write_text(OUTSIDE, encoding="utf-8")
    (root / "id_rsa").write_text(OUTSIDE, encoding="utf-8")
    (root / "password.key").write_text(OUTSIDE, encoding="utf-8")
    denied = root / "denied"
    denied.mkdir()
    (denied / "secret.txt").write_text(OUTSIDE, encoding="utf-8")
    workspace = Workspace.at(root, denied_paths=frozenset({denied.resolve()}))
    _install(monkeypatch, workspace)

    result = search_text(OUTSIDE)
    assert "1 match" not in result


def test_outside_workspace_path_is_rejected_before_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    _, outside_file = _outside_marker(tmp_path)
    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)
    read_paths: list[Path] = []

    result = search_text(
        OUTSIDE, str(outside_file), _hooks=SearchHooks(before_read=read_paths.append)
    )
    assert result.startswith("Error:")
    assert "OUTSIDE_MARKER" not in result
    assert read_paths == []


def test_listing_only_tree_is_never_opened_for_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    listed = root / "transcripts"
    listed.mkdir()
    (listed / "answer.txt").write_text(OUTSIDE, encoding="utf-8")
    workspace = Workspace.at(root, listing_only_paths=frozenset({listed.resolve()}))
    _install(monkeypatch, workspace)
    read_paths: list[Path] = []

    result = search_text(OUTSIDE, _hooks=SearchHooks(before_read=read_paths.append))
    assert "1 match" not in result
    assert read_paths == []


def test_hard_link_with_multiple_links_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    outside, outside_file = _outside_marker(tmp_path)
    del outside
    alias = root / "linked.txt"
    try:
        os.link(outside_file, alias)
    except OSError as exc:
        pytest.skip(f"BLOCKED: hard-link creation unavailable: {exc}")
    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)

    result = search_text(OUTSIDE)
    assert "1 match" not in result




def test_search_file_limit_is_applied_before_the_next_file_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    for index in range(4):
        (root / f"file-{index}.txt").write_text("ordinary", encoding="utf-8")
    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)
    monkeypatch.setattr(tools, "MAX_SEARCH_FILES", 2)
    read_paths: list[Path] = []
    result = search_text("never-present", _hooks=SearchHooks(before_read=read_paths.append))
    assert "2 files searched" in result
    assert len(read_paths) == 2


def test_total_directory_entry_enumeration_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    for name in ("alpha", "bravo", "charlie"):
        (root / name).write_text("ordinary", encoding="utf-8")
    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)
    monkeypatch.setattr(secure_search, "MAX_SEARCH_ENTRIES", 2)
    result = search_text("never-present")
    assert result.startswith("Error: search stopped safely:")
    assert "search entry limit" in result


def test_fifo_does_not_block_posix_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name != "posix":
        pytest.skip("BLOCKED: POSIX FIFO behavior cannot run on this platform")
    root = tmp_path / "workspace"
    root.mkdir()
    mkfifo = getattr(os, "mkfifo", None)
    if mkfifo is None:
        pytest.skip("BLOCKED: os.mkfifo is unavailable")
    mkfifo(root / "hostile-pipe")
    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)
    result_queue: queue.Queue[str] = queue.Queue()
    original_open = os.open
    opened_fifo = False

    def record_open(
        path: str | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal opened_fifo
        if path == "hostile-pipe":
            opened_fifo = True
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", record_open)

    def run_search() -> None:
        result_queue.put(search_text("never-present"))

    worker = threading.Thread(target=run_search, daemon=True)
    worker.start()
    try:
        result = result_queue.get(timeout=2)
    except queue.Empty:
        pytest.fail("search blocked while opening a FIFO entry")
    assert "never-present" in result
    assert not opened_fifo, "special FIFO should be rejected before os.open"


def test_windows_path_containment_is_volume_and_case_component_strict() -> None:
    assert _WindowsBackend.path_is_within(r"C:\Work\Root", r"C:\Work\Root\file.txt")
    assert not _WindowsBackend.path_is_within(r"C:\Work\Root", r"C:\Work\Rooted\file.txt")
    assert not _WindowsBackend.path_is_within(r"C:\Work\Root", r"D:\Work\Root\file.txt")
    assert not _WindowsBackend.path_is_within(r"C:\Work\Root", r"C:\work\Root\file.txt")
    assert _is_windows_device_name("CON")
    assert _is_windows_device_name("nul.txt")
    assert _is_windows_device_name("CONIN$")
    assert _is_windows_device_name("CONOUT$.txt")
    assert _is_windows_device_name("COM¹")
    assert _is_windows_device_name("LPT³.log:stream")
    assert not _is_windows_device_name("conifer.txt")


@pytest.mark.skipif(os.name != "nt", reason="BLOCKED: Windows device aliases require Windows")
@pytest.mark.parametrize("alias", ["CONIN$", "CONOUT$.txt", "COM¹", "LPT³.log:stream"])
def test_windows_device_alias_is_filtered_before_child_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, alias: str
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)
    original_resolve = workspace.resolve

    def resolve_alias(_workspace: Workspace, candidate: str) -> Path:
        if Path(candidate).name == alias:
            return root / alias
        return original_resolve(candidate)

    monkeypatch.setattr(Workspace, "resolve", resolve_alias)
    monkeypatch.setattr(_WindowsBackend, "enumerate", lambda _self, _handle, _limit: [(alias, 1)])

    def forbidden_open(
        _self: _WindowsBackend, _parent: int, name: str, _identity: int | None
    ) -> int:
        pytest.fail(f"reserved device alias reached child open: {name}")

    monkeypatch.setattr(_WindowsBackend, "open_child", forbidden_open)
    assert "1 match" not in search_text("unreachable")


def test_only_ntfs_is_supported_by_the_windows_backend() -> None:
    _WindowsBackend.require_supported_architecture("AMD64", 64)
    for machine, bits in (("x86", 32), ("ARM64", 64), ("AMD64", 32)):
        with pytest.raises(SecureSearchError, match="64-bit AMD64 required"):
            _WindowsBackend.require_supported_architecture(machine, bits)
    _WindowsBackend.require_case_insensitive_directory(0)
    with pytest.raises(SecureSearchError, match="case-sensitive Windows directories"):
        _WindowsBackend.require_case_insensitive_directory(1)
    _WindowsBackend.require_supported_filesystem("NTFS")
    _WindowsBackend.require_local_fixed_drive(_WindowsBackend.DRIVE_FIXED)
    for drive_type in (0, 2, 4, 5, 6):
        with pytest.raises(SecureSearchError, match="local fixed volume required"):
            _WindowsBackend.require_local_fixed_drive(drive_type)
    for filesystem in ("ReFS", "FAT32", "exFAT", "SMB"):
        with pytest.raises(SecureSearchError, match="unsupported Windows filesystem"):
            _WindowsBackend.require_supported_filesystem(filesystem)


@pytest.mark.skipif(os.name != "nt", reason="BLOCKED: Windows NTFS API unavailable")
def test_windows_case_sensitive_ntfs_workspace_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "case-sensitive"
    root.mkdir()
    probe = _WindowsBackend(Workspace.at(tmp_path))
    handle = probe.kernel32.CreateFileW(
        str(root),
        0x0100 | probe.FILE_READ_ATTRIBUTES,
        probe.FILE_SHARE_ALL,
        None,
        probe.OPEN_EXISTING,
        probe.FILE_FLAG_BACKUP_SEMANTICS | probe.FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        pytest.skip("BLOCKED: could not open a temporary directory for case-mode mutation")

    class FileCaseSensitiveInfo(ctypes.Structure):
        _fields_ = [("Flags", ctypes.c_uint32)]

    info = FileCaseSensitiveInfo(Flags=probe.FILE_CS_FLAG_CASE_SENSITIVE_DIR)
    try:
        changed = probe.kernel32.SetFileInformationByHandle(
            handle,
            probe.FILE_INFO_CASE_SENSITIVE,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not changed:
            pytest.skip("BLOCKED: NTFS case-sensitive directories are unavailable on this host")
    finally:
        probe.close(int(handle))

    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)
    try:
        result = search_text("never-present")
        assert result.startswith("Error: search stopped safely:")
        assert "case-sensitive Windows directories" in result
    finally:
        cleanup = probe.kernel32.CreateFileW(
            str(root),
            0x0100 | probe.FILE_READ_ATTRIBUTES,
            probe.FILE_SHARE_ALL,
            None,
            probe.OPEN_EXISTING,
            probe.FILE_FLAG_BACKUP_SEMANTICS | probe.FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        if cleanup != ctypes.c_void_p(-1).value:
            info.Flags = 0
            probe.kernel32.SetFileInformationByHandle(
                cleanup,
                probe.FILE_INFO_CASE_SENSITIVE,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            probe.close(int(cleanup))


@pytest.mark.skipif(os.name != "nt", reason="BLOCKED: Windows handle metadata unavailable")
def test_windows_enumerated_file_id_matches_open_handle_id(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "sample.txt").write_text("sample", encoding="utf-8")
    workspace = Workspace.at(root)
    backend = _WindowsBackend(workspace)
    root_handle = backend.open_root()
    child_handle: int | None = None
    try:
        entries = backend.enumerate(root_handle, secure_search.MAX_SEARCH_ENTRIES)
        name, enumerated_id = next(item for item in entries if item[0] == "sample.txt")
        child_handle = backend.open_child(root_handle, name, enumerated_id)
        identity = backend._identity(child_handle)
        assert identity[2] == 0
        assert identity[1] == enumerated_id
    finally:
        if child_handle is not None:
            backend.close(child_handle)
        backend.close(root_handle)


@pytest.mark.skipif(os.name != "nt", reason="BLOCKED: Windows handle metadata unavailable")
def test_windows_unknown_reparse_tag_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "sample.txt").write_text(OUTSIDE, encoding="utf-8")
    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)
    original = _WindowsBackend._attributes
    calls = 0

    def unknown_tag(self: _WindowsBackend, handle: int) -> tuple[int, int]:
        nonlocal calls
        calls += 1
        attrs, tag = original(self, handle)
        if calls >= 2:
            return attrs | self.FILE_ATTRIBUTE_REPARSE_POINT, 0xA000BEEF
        return attrs, tag

    monkeypatch.setattr(_WindowsBackend, "_attributes", unknown_tag)
    result = search_text(OUTSIDE)
    assert "1 match" not in result


@pytest.mark.skipif(os.name != "nt", reason="BLOCKED: Windows handle metadata unavailable")
def test_windows_final_path_failure_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "sample.txt").write_text(OUTSIDE, encoding="utf-8")
    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)

    def fail_final_path(self: _WindowsBackend, handle: int) -> str:
        raise OSError("injected final-path failure")

    monkeypatch.setattr(_WindowsBackend, "_final_path", fail_final_path)
    result = search_text(OUTSIDE)
    assert result.startswith("Error: search stopped safely:")
    assert "1 match" not in result


@pytest.mark.skipif(os.name == "nt", reason="BLOCKED: this test requires POSIX dir_fd APIs")
def test_posix_symlink_policy_refuses_internal_and_external_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "inside.txt").write_text(OUTSIDE, encoding="utf-8")
    (root / "internal-link.txt").symlink_to(root / "inside.txt")
    outside, outside_file = _outside_marker(tmp_path)
    del outside
    (root / "external-link.txt").symlink_to(outside_file)
    workspace = Workspace.at(root)
    _install(monkeypatch, workspace)

    result = search_text(OUTSIDE)
    assert "1 match" not in result
