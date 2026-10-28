from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

from scripts.package_fc_zip import REQUIRED_ENTRIES, build_archive, validate_archive


def _stage(tmp_path: Path) -> Path:
    root = tmp_path / "build"
    for name in REQUIRED_ENTRIES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture\n", encoding="utf-8")
    return root


def test_package_extracts_as_importable_runtime_without_source_checkout(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    repo = Path(__file__).resolve().parents[1]
    for path in repo.glob("*.py"):
        shutil.copyfile(path, root / path.name)
    shutil.copytree(repo / "scripts", root / "scripts", dirs_exist_ok=True)
    cache = root / "scripts" / "__pycache__" / "obsolete.pyc"
    cache.parent.mkdir(exist_ok=True)
    cache.write_bytes(b"stale")
    output = tmp_path / "function.zip"
    build_archive(root, output)
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert "scripts/build_weekly_package.py" in archive.namelist()
        assert not any("\\" in name or "__pycache__" in name for name in archive.namelist())
        archive.extractall(extracted)
    script = (
        "import pathlib, sys; sys.path.insert(0, sys.argv[1]); "
        "import fc_weekly_render, scripts.build_weekly_package, weekly_typst_export; "
        "root=pathlib.Path(sys.argv[1]); "
        "assert all(root in pathlib.Path(m.__file__).parents for m in "
        "(fc_weekly_render, scripts.build_weekly_package, weekly_typst_export)); "
        "assert callable(fc_weekly_render.handler)"
    )
    subprocess.run([sys.executable, "-I", "-c", script, str(extracted)],
                   cwd=tmp_path, check=True, capture_output=True, text=True)


@pytest.mark.parametrize("bad_name", [
    "scripts\\build_weekly_package.py", "../escape.py", "/absolute.py",
    "C:/drive.py", "__pycache__/bad.pyc", "windows.pyd", "function.zip",
])
def test_validator_rejects_linux_import_and_nested_package_failures(tmp_path: Path, bad_name: str) -> None:
    output = tmp_path / "invalid.zip"
    with zipfile.ZipFile(output, "w") as archive:
        for name in REQUIRED_ENTRIES:
            archive.writestr(name, "# fixture")
        info = zipfile.ZipInfo("placeholder")
        info.filename = bad_name
        info.orig_filename = bad_name
        archive.writestr(info, "bad")
    with pytest.raises(ValueError):
        validate_archive(output)


@pytest.mark.parametrize("missing", [
    "scripts/__init__.py", "scripts/build_weekly_package.py",
    "weekly_typst_export.py", "bs4/__init__.py", "requests/__init__.py",
    "knowledge_base/policy_corpus/policy_statements_core.jsonl",
])
def test_incomplete_package_never_replaces_good_output(tmp_path: Path, missing: str) -> None:
    root = _stage(tmp_path)
    (root / missing).unlink()
    output = tmp_path / "function.zip"
    output.write_bytes(b"previous good package")
    with pytest.raises(ValueError, match="Missing required"):
        build_archive(root, output)
    assert output.read_bytes() == b"previous good package"


def test_output_cannot_be_nested_inside_build_dir(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    with pytest.raises(ValueError, match="outside build_dir"):
        build_archive(root, root / "function.zip")


def test_builders_share_zip_validation_and_fail_on_native_command_errors() -> None:
    repo = Path(__file__).resolve().parents[1]
    powershell = (repo / "scripts/build_fc_package.ps1").read_text(encoding="utf-8")
    shell = (repo / "scripts/build_fc_package.sh").read_text(encoding="utf-8")
    assert "package_fc_zip.py" in powershell and "package_fc_zip.py" in shell
    assert "CreateFromDirectory" not in powershell
    assert powershell.count("if ($LASTEXITCODE -ne 0)") >= 3
    assert "knowledge_base" in shell
    assert "mock_articles.json" in powershell and "mock_articles.json" in shell
    assert '"agent"' in powershell and "for dir in agent" in shell
