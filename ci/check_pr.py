"""Kiểm nội dung commit PR bằng object Git, không tin file đã checkout hoặc chạy mã Python của PR."""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath

from manifest import MANIFEST_FILE, MODEL_NAME, REPORT_FILE, ManifestError, verify_manifest


def git(repo: Path, *args: str) -> bytes:
    try:
        return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, timeout=60).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise ManifestError(
            "Git: không đọc được commit/lịch sử PR; cần checkout fetch-depth: 0 và đúng base/head."
        ) from None


def commit(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").decode().strip()


def tree(repo: Path, head: str) -> dict[str, tuple[str, str, str]]:
    entries = {}
    for record in git(repo, "ls-tree", "-r", "-z", head).split(b"\0"):
        if record:
            metadata, path = record.split(b"\t", 1)
            entries[path.decode("utf-8")] = tuple(metadata.decode().split())
    return entries


def changed_pipelines(repo: Path, base: str, head: str) -> list[str]:
    changed = git(repo, "diff", "--name-only", "--no-renames", "-z", f"{base}...{head}", "--")
    models = set()
    for raw in changed.split(b"\0"):
        if not raw:
            continue
        path = raw.decode("utf-8")
        parts = path.split("/")
        if len(parts) < 3 or parts[0] != "pipelines" or not MODEL_NAME.fullmatch(parts[1]):
            raise ManifestError(f"{path}: mọi file thay đổi phải nằm trong pipelines/<model_name>/.")
        models.add(parts[1])
    if not models:
        raise ManifestError("pipelines/: PR không có pipeline thay đổi.")
    return sorted(models)


def _unique_keys(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"trường JSON trùng: {key}")
        result[key] = value
    return result


def _json(text: str, path: str) -> dict:
    try:
        value = json.loads(text, object_pairs_hook=_unique_keys)
        if not isinstance(value, dict):
            raise ValueError("phải là object JSON")
        return value
    except ValueError as exc:
        raise ManifestError(f"{path}: JSON không hợp lệ ({exc}).") from None


def _timestamp(value: str) -> datetime:
    at = datetime.fromisoformat(value)
    if at.tzinfo is None:
        raise ValueError("thiếu múi giờ")
    return at


def pipeline_files(repo: Path, head: str, model: str, entries: dict | None = None) -> dict[str, str]:
    """Đọc và kiểm đủ bộ file ở head; trả nội dung file đã ký, giữ nguyên cả CRLF."""
    if not MODEL_NAME.fullmatch(model):
        raise ManifestError(f"pipelines/{model}: tên model không hợp lệ.")
    folder = f"pipelines/{model}/"
    entries = tree(repo, head) if entries is None else entries
    contents = {}
    for path, (mode, kind, sha) in entries.items():
        if not path.startswith(folder):
            continue
        if mode != "100644" or kind != "blob":
            raise ManifestError(f"{path}: phải là file thường 100644, không symlink, submodule hay file thực thi.")
        try:
            contents[path.removeprefix(folder)] = git(repo, "cat-file", "blob", sha).decode("utf-8")
        except UnicodeError:
            raise ManifestError(f"{path}: nội dung không phải UTF-8.") from None
    for name in (MANIFEST_FILE, REPORT_FILE):
        if name not in contents:
            raise ManifestError(f"{folder}{name}: thiếu file bắt buộc; không được xóa cả pipeline.")
    manifest = _json(contents.pop(MANIFEST_FILE), folder + MANIFEST_FILE)
    report = _json(contents.pop(REPORT_FILE), folder + REPORT_FILE)
    try:
        if manifest.get("model_name") != model:
            raise ManifestError("model_name không khớp tên thư mục.")
        if type(manifest.get("version")) is not int or type(manifest.get("manifest_version")) is not int:
            raise ManifestError("version và manifest_version phải là số nguyên.")
        expected = manifest.get("files")
        if isinstance(expected, dict):
            for path in expected:
                if path != PurePosixPath(path).as_posix() or "\0" in path or path == ".":
                    raise ManifestError(f"Đường dẫn file '{path}' không ở dạng POSIX chuẩn.")
        verify_manifest(manifest, contents)
        approved_at = _timestamp(manifest["approved_at"])
    except (ManifestError, ValueError, TypeError) as exc:
        raise ManifestError(f"{folder}{MANIFEST_FILE}: {exc}") from None
    approval = report.get("approval")
    if not isinstance(approval, dict):
        raise ManifestError(f"{folder}{REPORT_FILE}: thiếu chữ ký approval.")
    for key in ("run_id", "version", "files_hash"):
        if type(report.get(key)) is not type(manifest[key]) or report[key] != manifest[key]:
            raise ManifestError(f"{folder}{REPORT_FILE}: {key} không khớp {folder}{MANIFEST_FILE}.")
    signed = {
        "decision": "approved",
        "reviewer": manifest["reviewer"],
        "version": manifest["version"],
        "files_hash": manifest["files_hash"],
    }
    for key, value in signed.items():
        if type(approval.get(key)) is not type(value) or approval[key] != value:
            raise ManifestError(
                f"{folder}{REPORT_FILE}: approval.{key} không khớp chữ ký duyệt trong {folder}{MANIFEST_FILE}."
            )
    try:
        if _timestamp(approval.get("at", "")) != approved_at:
            raise ValueError("khác thời điểm")
    except (ValueError, TypeError):
        raise ManifestError(
            f"{folder}{REPORT_FILE}: approval.at không khớp approved_at hợp lệ trong manifest."
        ) from None
    created_by = report.get("created_by")
    if not isinstance(created_by, str) or not created_by.strip():
        raise ManifestError(f"{folder}{REPORT_FILE}: thiếu created_by hợp lệ của người tạo run.")
    if report.get("status") != "APPROVED" or created_by == manifest["reviewer"]:
        raise ManifestError(f"{folder}{REPORT_FILE}: cần trạng thái APPROVED và người duyệt khác người tạo run.")
    if report.get("files") != manifest["files"]:
        raise ManifestError(f"{folder}{REPORT_FILE}: danh sách files không khớp manifest.")
    spec = report.get("spec")
    transform = spec.get("transform") if isinstance(spec, dict) else None
    if not isinstance(transform, dict) or transform.get("model_name") != model:
        raise ManifestError(f"{folder}{REPORT_FILE}: spec.transform.model_name không khớp thư mục.")
    return contents


def check_pr(repo: Path, base: str, head: str) -> list[str]:
    base, head = commit(repo, base), commit(repo, head)
    models = changed_pipelines(repo, base, head)
    entries = tree(repo, head)
    for model in models:
        pipeline_files(repo, head, model, entries)
    return models


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    try:
        for model in check_pr(args.repo, args.base, args.head):
            print(model)
    except (ManifestError, UnicodeError) as exc:
        print(f"Kiểm PR thất bại: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
