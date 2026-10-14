"""Disposable Windows process gates for profile-operation crash recovery.

Runs three independent Python managers. No browser is started and no existing
portable Data directory is opened. The parent owns and removes its temporary
root; the child deliberately exits while holding the Windows named mutex.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import queue
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nevision_win import AppPaths, NeVisionError, Storage, canonical_path_key  # noqa: E402

CHILD_TIMEOUT_SECONDS = 15
CRASH_EXIT_CODE = 73
SYNTHETIC_STATE = b"neantik-two-manager-synthetic-state-v1"
ROOT_MARKER = ".neantik-two-manager-disposable"


def _emit(**fields: Any) -> None:
    print(json.dumps(fields, sort_keys=True, separators=(",", ":")), flush=True)


def _require_disposable_root(root: Path) -> None:
    expected_parent = Path(tempfile.gettempdir()).resolve()
    if (not root.is_dir() or root.is_symlink() or root.resolve().parent != expected_parent
            or not root.name.startswith("neantik-two-manager-gate-")
            or not (root / ROOT_MARKER).is_file()
            or (root / ROOT_MARKER).read_text(encoding="ascii") != "synthetic-only-v1"):
        raise RuntimeError("not_disposable_root")


def _row_exists(root: Path, profile_id: str) -> bool:
    # sqlite3.Connection.__exit__ commits/rolls back but does not close the DB
    # handle; an open handle prevents deterministic temp cleanup on Windows.
    with contextlib.closing(sqlite3.connect(AppPaths(root).database, timeout=2)) as db:
        return db.execute("SELECT 1 FROM profiles WHERE id = ?", (profile_id,)).fetchone() is not None


def _operation_files(root: Path) -> list[Path]:
    return sorted(AppPaths(root).operations.glob("*.json"))


def _deleted_entries(root: Path) -> list[Path]:
    deleted = AppPaths(root).data / "Deleted"
    return sorted(deleted.iterdir()) if deleted.exists() else []


def _state_snapshot(root: Path, profile_id: str) -> dict[str, Any]:
    """Logical state only: no raw profile contents or database/WAL bytes."""
    source = AppPaths(root).profiles / profile_id
    entries = _deleted_entries(root)
    journals = _operation_files(root)
    return {
        "db_row": _row_exists(root, profile_id),
        "source_exists": source.exists(),
        "deleted_names": [item.name for item in entries],
        "deleted_state_sha256": [
            hashlib.sha256((item / "state.bin").read_bytes()).hexdigest()
            if (item / "state.bin").is_file() else None for item in entries
        ],
        "journal_names": [item.name for item in journals],
        "journal_sha256": [hashlib.sha256(item.read_bytes()).hexdigest() for item in journals],
    }


def _read_line_bounded(process: subprocess.Popen[str]) -> dict[str, Any]:
    received: queue.Queue[str] = queue.Queue(maxsize=1)

    def reader() -> None:
        try:
            received.put(process.stdout.readline() if process.stdout else "")
        except (OSError, ValueError):
            received.put("")

    threading.Thread(target=reader, daemon=True).start()
    try:
        line = received.get(timeout=CHILD_TIMEOUT_SECONDS)
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError("record_not_object")
        return record
    except queue.Empty as exc:
        raise RuntimeError("child_ready_timeout") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("child_ready_invalid") from exc


def _command(mode: str, root: Path, profile_id: str) -> list[str]:
    return [sys.executable, str(Path(__file__).resolve()), mode, "--root", str(root), "--profile-id", profile_id]


def _spawn(mode: str, root: Path, profile_id: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        _command(mode, root, profile_id),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(ROOT),
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def _finish(process: subprocess.Popen[str], input_text: str = "") -> tuple[int, dict[str, Any]]:
    try:
        output, _ = process.communicate(input=input_text, timeout=CHILD_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.communicate(timeout=CHILD_TIMEOUT_SECONDS)
        raise RuntimeError("child_exit_timeout") from exc
    try:
        record = json.loads(output.strip())
        if not isinstance(record, dict):
            raise ValueError("record_not_object")
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("child_result_invalid") from exc
    return process.returncode, record


def _worker_hold_delete(root: Path, profile_id: str) -> int:
    _require_disposable_root(root)
    storage = Storage(AppPaths(root))
    source_key = canonical_path_key(storage.profile_path(profile_id))
    original_replace = os.replace

    def pause_after_move(source: os.PathLike[str] | str, target: os.PathLike[str] | str) -> None:
        original_replace(source, target)
        if canonical_path_key(Path(source)) == source_key:
            # This executes inside delete_profile's __data_recovery__ mutex,
            # after the durable journal and rename, before the SQLite DELETE.
            _emit(event="moved")
            command = sys.stdin.readline().strip()
            if command == "CRASH":
                os._exit(CRASH_EXIT_CODE)
            os._exit(74)

    os.replace = pause_after_move
    storage.delete_profile(profile_id)
    _emit(event="unexpected_delete_completion")
    return 1


def _worker_hold_restore(root: Path, profile_id: str) -> int:
    """Exit at the real restore publish/DB-commit boundary on parent command."""
    _require_disposable_root(root)
    storage = Storage(AppPaths(root))
    source_root = canonical_path_key(storage.paths.profiles)
    original_replace = os.replace

    def pause_after_publish(source: os.PathLike[str] | str, target: os.PathLike[str] | str) -> None:
        source_path = Path(source)
        target_path = Path(target)
        source_was_directory = source_path.is_dir()
        original_replace(source, target)
        target_id = target_path.name
        if (
            source_was_directory
            and source_path.name.startswith(".restore-")
            and canonical_path_key(source_path.parent) == source_root
            and canonical_path_key(target_path.parent) == source_root
            and len(target_id) == 32
            and all(character in "0123456789abcdef" for character in target_id.casefold())
        ):
            # Restore journal is durable and directory is visible; DB INSERT has
            # not started. Parent inspects this exact state before inducing exit.
            _emit(event="restore_published", restored_id=target_id)
            command = sys.stdin.readline().strip()
            os._exit(CRASH_EXIT_CODE if command == "CRASH" else 74)

    os.replace = pause_after_publish
    archive = root / "synthetic-restore-source.zip"
    storage.restore_profile(archive, "Restored after process interruption")
    _emit(event="unexpected_restore_completion")
    return 1


def _worker_contend(root: Path, profile_id: str) -> int:
    _require_disposable_root(root)
    try:
        Storage(AppPaths(root))
    except NeVisionError as exc:
        if "занят другой операцией" in str(exc):
            _emit(result="busy")
            return 0
        _emit(result="unexpected_storage_error")
        return 2
    _emit(result="unexpected_access")
    return 3


def _worker_recover(root: Path, profile_id: str) -> int:
    _require_disposable_root(root)
    try:
        Storage(AppPaths(root))
    except NeVisionError:
        _emit(result="recovery_error")
        return 2
    _emit(result="recovered")
    return 0


def run_gate() -> dict[str, Any]:
    if os.name != "nt":
        return {"status": "NOT_RUN", "reason": "windows_only"}
    root = Path(tempfile.mkdtemp(prefix="neantik-two-manager-gate-"))
    owned: list[subprocess.Popen[str]] = []
    checks: dict[str, bool] = {}
    reason = "ok"
    try:
        (root / ROOT_MARKER).write_text("synthetic-only-v1", encoding="ascii")
        storage = Storage(AppPaths(root))
        profile_id = storage.save_profile({"name": "Synthetic process gate"})
        (storage.profile_path(profile_id) / "state.bin").write_bytes(SYNTHETIC_STATE)
        child = _spawn("hold-delete", root, profile_id)
        owned.append(child)
        ready = _read_line_bounded(child)
        checks["held_at_journal_move"] = ready.get("event") == "moved" and child.poll() is None
        if not checks["held_at_journal_move"]:
            raise RuntimeError("child_not_at_barrier")
        before = _state_snapshot(root, profile_id)
        checks["pre_crash_state"] = (
            before["db_row"] and not before["source_exists"]
            and len(before["deleted_names"]) == 1
            and before["deleted_state_sha256"] == [hashlib.sha256(SYNTHETIC_STATE).hexdigest()]
            and len(before["journal_names"]) == 1
        )
        contender = _spawn("contend", root, profile_id)
        owned.append(contender)
        contender_code, contender_result = _finish(contender)
        checks["second_manager_busy"] = contender_code == 0 and contender_result.get("result") == "busy"
        checks["second_manager_unchanged"] = _state_snapshot(root, profile_id) == before
        if not all(checks.values()):
            raise RuntimeError("concurrency_invariant_failed")
        if child.stdin is None:
            raise RuntimeError("child_stdin_missing")
        child.stdin.write("CRASH\n")
        child.stdin.flush()
        child.wait(timeout=CHILD_TIMEOUT_SECONDS)
        checks["controlled_crash"] = child.returncode == CRASH_EXIT_CODE
        if not checks["controlled_crash"]:
            raise RuntimeError("crash_exit_mismatch")
        recovery = _spawn("recover", root, profile_id)
        owned.append(recovery)
        recovery_code, recovery_result = _finish(recovery)
        checks["third_manager_recovered"] = recovery_code == 0 and recovery_result.get("result") == "recovered"
        after = _state_snapshot(root, profile_id)
        checks["data_restored"] = (
            after["db_row"] and after["source_exists"]
            and (storage.profile_path(profile_id) / "state.bin").read_bytes() == SYNTHETIC_STATE
        )
        checks["journal_cleared"] = not after["journal_names"] and not after["deleted_names"]
        if not all(checks.values()):
            reason = "recovery_invariant_failed"
    except (OSError, sqlite3.Error, NeVisionError, RuntimeError, subprocess.TimeoutExpired) as exc:
        reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
    finally:
        for process in owned:
            if process.poll() is None:
                process.kill()
            try:
                process.communicate(timeout=CHILD_TIMEOUT_SECONDS)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
        try:
            _require_disposable_root(root)
            shutil.rmtree(root)
            if root.exists():
                reason = "cleanup_incomplete"
        except (OSError, RuntimeError) as exc:
            reason = f"cleanup_failed_{type(exc).__name__}"
    return {"status": "PASS" if reason == "ok" and all(checks.values()) else "FAIL", "reason": reason, "checks": checks}


def run_restore_crash_gate() -> dict[str, Any]:
    """Crash a real restore worker after publish, then verify startup recovery."""
    if os.name != "nt":
        return {"status": "NOT_RUN", "reason": "windows_only"}
    root = Path(tempfile.mkdtemp(prefix="neantik-two-manager-gate-"))
    owned: list[subprocess.Popen[str]] = []
    checks: dict[str, bool] = {}
    reason = "ok"
    try:
        (root / ROOT_MARKER).write_text("synthetic-only-v1", encoding="ascii")
        storage = Storage(AppPaths(root))
        source_id = storage.save_profile({"name": "Synthetic restore source"})
        source_state = storage.profile_path(source_id) / "Default" / "state.bin"
        source_state.parent.mkdir(parents=True)
        source_state.write_bytes(SYNTHETIC_STATE)
        archive = storage.backup_profile(source_id)
        shutil.copyfile(archive, root / "synthetic-restore-source.zip")

        child = _spawn("hold-restore", root, source_id)
        owned.append(child)
        ready = _read_line_bounded(child)
        restored_id = ready.get("restored_id")
        checks["child_paused_after_publish"] = (
            ready.get("event") == "restore_published"
            and isinstance(restored_id, str)
            and len(restored_id) == 32
            and child.poll() is None
        )
        if not checks["child_paused_after_publish"]:
            raise RuntimeError("restore_child_not_at_publish_barrier")

        journal_files = _operation_files(root)
        restored_path = storage.profile_path(restored_id)
        checks["journal_and_directory_published"] = (
            len(journal_files) == 1
            and restored_path.is_dir()
            and (restored_path / "Default" / "state.bin").read_bytes() == SYNTHETIC_STATE
        )
        journal = json.loads(journal_files[0].read_text(encoding="utf-8")) if journal_files else {}
        checks["database_insert_not_started"] = (
            not _row_exists(root, restored_id)
            and journal.get("operation") == "restore"
            and journal.get("profile", {}).get("id") == restored_id
        )
        checks["source_profile_untouched"] = (
            _row_exists(root, source_id)
            and source_state.read_bytes() == SYNTHETIC_STATE
        )

        contender = _spawn("contend", root, source_id)
        owned.append(contender)
        contender_code, contender_result = _finish(contender)
        checks["second_manager_busy"] = (
            contender_code == 0 and contender_result.get("result") == "busy"
        )
        checks["state_unchanged_during_contention"] = (
            len(_operation_files(root)) == 1
            and restored_path.is_dir()
            and not _row_exists(root, restored_id)
        )

        if child.stdin is None:
            raise RuntimeError("restore_child_stdin_missing")
        child.stdin.write("CRASH\n")
        child.stdin.flush()
        child.wait(timeout=CHILD_TIMEOUT_SECONDS)
        checks["controlled_process_crash"] = child.returncode == CRASH_EXIT_CODE
        if not checks["controlled_process_crash"]:
            raise RuntimeError("restore_crash_exit_mismatch")

        recovery = _spawn("recover", root, source_id)
        owned.append(recovery)
        recovery_code, recovery_result = _finish(recovery)
        checks["startup_recovery_succeeded"] = (
            recovery_code == 0 and recovery_result.get("result") == "recovered"
        )
        checks["restored_profile_and_data_recovered"] = (
            _row_exists(root, restored_id)
            and Storage(AppPaths(root)).get_profile(restored_id)["name"]
            == "Restored after process interruption"
            and (restored_path / "Default" / "state.bin").read_bytes() == SYNTHETIC_STATE
            and source_state.read_bytes() == SYNTHETIC_STATE
        )
        checks["journal_cleared"] = not _operation_files(root)
        if not all(checks.values()):
            reason = "restore_recovery_invariant_failed"
    except (OSError, sqlite3.Error, NeVisionError, RuntimeError, subprocess.TimeoutExpired) as exc:
        reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
    finally:
        for process in owned:
            if process.poll() is None:
                process.kill()
            try:
                process.communicate(timeout=CHILD_TIMEOUT_SECONDS)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
        try:
            _require_disposable_root(root)
            shutil.rmtree(root)
            if root.exists():
                reason = "cleanup_incomplete"
        except (OSError, RuntimeError) as exc:
            reason = f"cleanup_failed_{type(exc).__name__}"
    return {"status": "PASS" if reason == "ok" and all(checks.values()) else "FAIL",
            "reason": reason, "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("hold-delete", "hold-restore", "contend", "recover"))
    parser.add_argument("--root", type=Path)
    parser.add_argument("--profile-id")
    args = parser.parse_args()
    if args.mode:
        if not args.root or not args.profile_id:
            parser.error("worker mode requires root and profile ID")
        if args.mode == "hold-delete":
            return _worker_hold_delete(args.root, args.profile_id)
        if args.mode == "hold-restore":
            return _worker_hold_restore(args.root, args.profile_id)
        if args.mode == "contend":
            return _worker_contend(args.root, args.profile_id)
        return _worker_recover(args.root, args.profile_id)
    report = run_gate()
    _emit(**report)
    return {"PASS": 0, "FAIL": 1, "NOT_RUN": 3}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
