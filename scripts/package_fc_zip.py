"""Build and validate a Linux FC archive on Windows or Linux."""
from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

REQUIRED_ENTRIES = (
    "main.py", "fc_weekly_render.py", "fc_candidate_publish.py",
    "fc_practice.py", "practice_coach.py", "practice_demo.py",
    "practice_links.py", "practice_store.py", "weekly_typst_export.py",
    "requirements.txt", "question_bank.py", "scripts/__init__.py",
    "scripts/build_weekly_package.py", "scripts/validate_daily_brief.py",
    "data/question_bank/shenlun_question_bank_v3_a.csv",
    "knowledge_base/policy_corpus/policy_statements_core.jsonl",
    "knowledge_base/topic_knowledge/article_index.jsonl",
    "bs4/__init__.py", "requests/__init__.py", "reportlab/__init__.py",
)


def validate_archive(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP entries")
        for name in names:
            parts = PurePosixPath(name).parts
            if "\\" in name or name.startswith("/") or ".." in parts or ":" in name:
                raise ValueError(f"Invalid Linux ZIP path: {name}")
            if any(part in {"__pycache__", ".pytest_cache", ".git"} for part in parts):
                raise ValueError(f"Build cache in ZIP: {name}")
            if PurePosixPath(name).suffix.lower() in {".pyc", ".pyo", ".pyd", ".zip"}:
                raise ValueError(f"Unsupported deployment file: {name}")
        missing = sorted(set(REQUIRED_ENTRIES) - set(names))
        if missing:
            raise ValueError(f"Missing required ZIP entries: {', '.join(missing)}")
        bad = archive.testzip()
        if bad:
            raise ValueError(f"ZIP integrity check failed: {bad}")


def build_archive(build_dir: Path, output_zip: Path) -> None:
    root = build_dir.resolve(strict=True)
    output = output_zip.resolve()
    if not root.is_dir():
        raise ValueError("build_dir must be a directory")
    if output == root or root in output.parents:
        raise ValueError("output_zip must be outside build_dir")
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink in build directory: {path.relative_to(root)}")
        if path.is_file():
            if any(part in {"__pycache__", ".pytest_cache"} for part in path.relative_to(root).parts):
                continue
            if path.suffix.lower() not in {".pyc", ".pyo"}:
                files.append(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Publish only a complete, validated archive; preserve prior good output on failure.
    with tempfile.TemporaryDirectory(prefix="fc-zip-", dir=output.parent) as temporary:
        staging = Path(temporary) / "function.zip"
        with zipfile.ZipFile(staging, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, arcname=path.relative_to(root).as_posix())
        validate_archive(staging)
        staging.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_dir", type=Path)
    parser.add_argument("output_zip", type=Path)
    args = parser.parse_args()
    build_archive(args.build_dir, args.output_zip)
    print(f"Built validated Linux FC package: {args.output_zip}")


if __name__ == "__main__":
    main()
