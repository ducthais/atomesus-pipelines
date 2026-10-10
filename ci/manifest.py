"""Manifest của một pipeline đã duyệt: bằng chứng bộ file trong pull request đúng là bộ Reviewer đã ký.

Ghi cùng commit P16 tại `pipelines/<model_name>/manifest.json` (src/codegen/deploy.py). CI của repo pipeline và
service deployer kiểm lại trước khi cài: sha256 từng file và files_hash phải khớp chữ ký duyệt, run_report.json mang
đúng chữ ký đó. Chỉ dùng thư viện chuẩn để deployer chạy độc lập với backend; cách băm giống hệt
`src.codegen.render.file_hashes`.
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import PurePosixPath

MANIFEST_VERSION = 1
MANIFEST_FILE = "manifest.json"
REPORT_FILE = "run_report.json"
# Trùng IDENTIFIER của Spec: tên model đi vào tên nhánh và đường dẫn thư mục nên phải chặt.
MODEL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


class ManifestError(ValueError):
    """Manifest hoặc bộ file không khớp chữ ký duyệt; thông báo tiếng Việt, an toàn để trả cho người dùng."""


def project_dir(model_name: str) -> str:
    """Thư mục của pipeline trong repo pipeline."""
    if not isinstance(model_name, str) or not MODEL_NAME.fullmatch(model_name):
        raise ManifestError(f"Tên model '{model_name}' không hợp lệ.")
    return f"pipelines/{model_name}"


def hash_files(files: dict[str, str]) -> tuple[dict[str, str], str]:
    """sha256 từng file và files_hash của cả bộ, cùng thuật toán với chữ ký duyệt."""
    hashes = {path: "sha256:" + hashlib.sha256(content.encode()).hexdigest() for path, content in sorted(files.items())}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return hashes, f"sha256:{digest}"


def _check_paths(paths) -> None:
    # Chỉ nhận đường dẫn tương đối kiểu POSIX nằm trong thư mục pipeline: không '/' đầu, không '\', không '..', không
    # ':' (ổ đĩa Windows như C:/x.sql hay c:x.sql). Đường dẫn phải ở dạng chuẩn (không './', '//', '/' cuối) để không
    # có bí danh: './manifest.json' hay 'a/./b.sql' trỏ cùng file với tên khác. Tên dành riêng so không phân biệt hoa
    # thường vì hệ file không phân biệt (Windows, macOS) coi 'Manifest.json' là cùng một file.
    seen = set()
    for path in paths:
        if not isinstance(path, str):
            raise ManifestError("Đường dẫn file trong bộ file đã duyệt phải là chuỗi.")
        normalized = PurePosixPath(path)
        parts = normalized.parts
        unsafe = not parts or path.startswith("/") or "\\" in path or ":" in path or ".." in parts or "\0" in path
        # Windows bỏ dấu chấm/khoảng trắng cuối tên và không phân biệt hoa thường: không nhận các bí danh này.
        unsafe = unsafe or any(part.rstrip(". ") != part for part in parts) or path.casefold() in seen
        reserved = str(normalized).casefold() in (MANIFEST_FILE, REPORT_FILE)
        if unsafe or str(normalized) != path or reserved:
            raise ManifestError(f"Đường dẫn file '{path}' không hợp lệ trong bộ file đã duyệt.")
        seen.add(path.casefold())


def load_json(text: str, name: str) -> dict:
    """Đọc một file JSON object của repo pipeline (manifest.json, run_report.json); hỏng hay sai kiểu ra ManifestError."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError, RecursionError):
        raise ManifestError(f"{name} không phải JSON hợp lệ.") from None
    if not isinstance(data, dict):
        raise ManifestError(f"{name} phải là một JSON object.")
    return data


def build_manifest(
    *, run_id: str, version: int, model_name: str, files: dict[str, str], reviewer: str, approved_at: datetime
) -> dict:
    """Manifest cho đúng bộ file đã duyệt (4 + N file, không gồm run_report.json và chính manifest)."""
    project_dir(model_name)
    if not files:
        raise ManifestError("Bộ file đã duyệt trống nên không dựng được manifest.")
    _check_paths(files)
    hashes, files_hash = hash_files(files)
    return {
        "manifest_version": MANIFEST_VERSION,
        "run_id": run_id,
        "version": version,
        "model_name": model_name,
        "files_hash": files_hash,
        "files": hashes,
        "reviewer": reviewer,
        "approved_at": approved_at.isoformat(),
    }


def verify_manifest(manifest: dict, files: dict[str, str]) -> None:
    """Kiểm bộ file (không gồm run_report.json, manifest.json) khớp manifest; lệch thì ManifestError."""
    if not isinstance(manifest, dict):
        raise ManifestError("Manifest phải là một JSON object.")
    version = manifest.get("manifest_version")
    if type(version) is not int or version != MANIFEST_VERSION:
        raise ManifestError(f"manifest_version phải là {MANIFEST_VERSION}.")
    for key in ("run_id", "model_name", "files_hash", "reviewer", "approved_at"):
        if not isinstance(manifest.get(key), str) or not manifest[key]:
            raise ManifestError(f"Manifest thiếu trường {key}.")
    # bool là lớp con của int trong Python: `true` trong JSON không được coi là version 1.
    if type(manifest.get("version")) is not int or manifest["version"] < 1:
        raise ManifestError("Manifest thiếu version hợp lệ.")
    project_dir(manifest["model_name"])
    expected = manifest.get("files")
    if not isinstance(expected, dict) or not expected:
        raise ManifestError("Manifest thiếu danh sách file.")
    _check_paths(expected)
    if not all(isinstance(digest, str) for digest in expected.values()):
        raise ManifestError("sha256 của từng file trong manifest phải là chuỗi.")
    if not isinstance(files, dict) or not all(
        isinstance(path, str) and isinstance(text, str) for path, text in files.items()
    ):
        raise ManifestError("Bộ file cần kiểm phải gồm đường dẫn và nội dung dạng chuỗi.")
    _check_paths(files)
    hashes, files_hash = hash_files(files)
    missing, extra = sorted(set(expected) - set(hashes)), sorted(set(hashes) - set(expected))
    if missing or extra:
        raise ManifestError(f"Bộ file khác manifest: thiếu {missing or 'không'}, thừa {extra or 'không'}.")
    changed = sorted(path for path, digest in hashes.items() if expected[path] != digest)
    if changed:
        raise ManifestError(f"sha256 không khớp manifest: {changed}.")
    if files_hash != manifest["files_hash"]:
        raise ManifestError("files_hash của bộ file không khớp chữ ký duyệt trong manifest.")


def _same_time(left, right) -> bool:
    # Manifest ghi `datetime.isoformat()` (+00:00), RunReport ghi kiểu pydantic (Z): so thời điểm, không so chuỗi.
    try:
        return datetime.fromisoformat(left) == datetime.fromisoformat(right)
    except (TypeError, ValueError):
        return False


def verify_report(manifest: dict, report: dict) -> None:
    """Kiểm run_report.json đi cùng pipeline mang đúng chữ ký duyệt ghi trong manifest (đã qua verify_manifest)."""
    if not isinstance(report, dict):
        raise ManifestError("run_report.json phải là một JSON object.")
    approval = report.get("approval")
    spec = report.get("spec")
    transform = spec.get("transform") if isinstance(spec, dict) else None
    model_name = transform.get("model_name") if isinstance(transform, dict) else None
    signed = (
        isinstance(approval, dict)
        and approval.get("decision") == "approved"
        and approval.get("reviewer") == manifest["reviewer"]
        and approval.get("files_hash") == report.get("files_hash") == manifest["files_hash"]
        and type(approval.get("version")) is int
        and type(report.get("version")) is int
        and approval["version"] == report["version"] == manifest["version"]
        and _same_time(approval.get("at"), manifest["approved_at"])
        and report.get("run_id") == manifest["run_id"]
        and model_name == manifest["model_name"]
    )
    if not signed:
        raise ManifestError(
            "run_report.json không khớp chữ ký duyệt trong manifest (run_id, version, files_hash, Reviewer)."
        )
