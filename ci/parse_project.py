"""Dựng project dbt tạm từ scaffold tin cậy và các blob đã kiểm của pipeline rồi chạy dbt parse."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from check_pr import commit, pipeline_files
from manifest import ManifestError

ROOT = Path(__file__).resolve().parents[1]
PASSTHROUGH_ENV = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA")


def parse_project(
    repo: Path, head: str, model: str, scaffold: Path = ROOT / "_scaffold/dbt_project", timeout: int = 120
) -> None:
    if timeout < 1 or timeout > 600:
        raise ManifestError("dbt parse: timeout phải từ 1 đến 600 giây.")
    files = pipeline_files(repo, commit(repo, head), model)
    with TemporaryDirectory(prefix="pipeline-parse-") as temporary:
        project = Path(temporary) / "dbt_project"
        shutil.copytree(scaffold, project)
        for name, content in files.items():
            if not name.startswith("dbt_project/"):
                continue
            relative = name.removeprefix("dbt_project/")
            # Cấu hình, profile và macro dùng bản trên base; PR chỉ đưa model sinh ra vào project.
            if not relative.startswith("models/") or Path(relative).suffix not in (".sql", ".yml", ".yaml"):
                raise ManifestError(f"pipelines/{model}/{name}: dbt parse chỉ nhận SQL/YAML trong models/.")
            target = project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content.encode("utf-8"))
        env = {key: os.environ[key] for key in PASSTHROUGH_ENV if key in os.environ}
        env.update(
            WAREHOUSE_PATH=str(Path(temporary) / "warehouse.duckdb"),
            WAREHOUSE_TIMEZONE="UTC",
            DBT_SEND_ANONYMOUS_USAGE_STATS="false",
            DO_NOT_TRACK="1",
            PYTHONIOENCODING="utf-8",
        )
        command = [
            sys.executable,
            "-c",
            "from dbt.cli.main import cli; cli()",
            "parse",
            "--no-partial-parse",
            "--project-dir",
            str(project),
            "--profiles-dir",
            str(project),
        ]
        with TemporaryDirectory(prefix="pipeline-log-") as log_directory:
            with (Path(log_directory) / "dbt.log").open("w+b") as log:
                try:
                    result = subprocess.run(
                        command, cwd=temporary, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout
                    )
                    error = "dbt parse thất bại" if result.returncode else ""
                except subprocess.TimeoutExpired:
                    error = f"dbt parse chạy quá {timeout} giây"
                log.seek(0, os.SEEK_END)
                log.seek(max(0, log.tell() - 4000))
                tail = log.read().decode("utf-8", errors="replace").strip()
            if error:
                raise ManifestError(f"pipelines/{model}/dbt_project: {error}.\n{tail}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", help="Tên pipeline đã được check_pr.py kiểm.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--head", required=True)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    try:
        parse_project(args.repo, args.head, args.model, timeout=args.timeout)
    except (ManifestError, OSError) as exc:
        print(f"Kiểm dbt thất bại: {exc}", file=sys.stderr)
        return 1
    print(f"pipelines/{args.model}: dbt parse thành công.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
