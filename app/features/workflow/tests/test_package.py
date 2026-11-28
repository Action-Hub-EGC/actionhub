"""Tests for the workflow package format and upload flow (#14)."""

import io
import os
import stat
import zipfile
from types import SimpleNamespace

import pytest

from app.features.auth.repositories import UserRepository
from app.features.hubfile.services import HubfileService
from app.features.workflow.models import WorkflowDataset
from app.features.workflow.package import PackageValidator
from app.features.workflow.services import WorkflowDatasetService

pytestmark = pytest.mark.service

MANIFEST = """name: demo-workflow
version: 1.0.0
description: A demo workflow used by the package tests
license: MIT
authors:
  - name: Ada Lovelace
    affiliation: Analytical Engine Lab
tags:
  - ci
  - demo
"""

WORKFLOW = """name: Demo
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""


def make_zip(extra=None, manifest=MANIFEST, workflow=WORKFLOW):
    files = {
        "actionhub.yaml": manifest,
        "workflow.yml": workflow,
        "README.md": "# Demo workflow\n\nThis is a demo.",
        "LICENSE": "MIT License\n\nCopyright (c) 2026",
    }
    if extra:
        files.update(extra)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_valid_package_passes_validation():
    result = PackageValidator().validate_zip(make_zip({"CHANGELOG.md": "## 1.0.0", "fixtures/input.txt": "x"}))

    assert result.valid is True
    assert result.issues == []
    assert result.manifest["name"] == "demo-workflow"
    assert result.workflow_yaml.startswith("name: Demo")
    assert "fixtures/input.txt" in result.files


def test_missing_required_file_is_reported():
    data = make_zip()
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(buffer, "w") as target:
        for info in source.infolist():
            if info.filename != "LICENSE":
                target.writestr(info, source.read(info))

    result = PackageValidator().validate_zip(buffer.getvalue())

    assert result.valid is False
    assert any("LICENSE" in issue.message for issue in result.issues)


def test_invalid_manifest_field_is_reported():
    result = PackageValidator().validate_zip(make_zip(manifest=MANIFEST.replace("version: 1.0.0", "version: one")))

    assert result.valid is False
    assert any(issue.field == "version" for issue in result.issues)


def test_malformed_workflow_is_reported():
    result = PackageValidator().validate_zip(make_zip(workflow="name: demo\njobs: [\n"))

    assert result.valid is False
    assert any(issue.file == "workflow.yml" and issue.line for issue in result.issues)


def test_zip_slip_is_rejected():
    data = make_zip()
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(buffer, "w") as target:
        for info in source.infolist():
            target.writestr(info, source.read(info))
        target.writestr("../evil.txt", "bad")

    result = PackageValidator().validate_zip(buffer.getvalue())

    assert result.valid is False
    assert any("Ruta no permitida" in issue.message for issue in result.issues)


def test_unknown_top_level_file_is_rejected():
    result = PackageValidator().validate_zip(make_zip({"extra.txt": "nope"}))

    assert result.valid is False
    assert any("extra.txt" in issue.message for issue in result.issues)


def test_file_name_longer_than_the_database_column_is_rejected():
    long_name = "fixtures/" + ("a" * 115) + ".txt"

    result = PackageValidator().validate_zip(make_zip({long_name: "x"}))

    assert result.valid is False
    assert any("120 caracteres" in issue.message for issue in result.issues)


def test_tags_that_do_not_fit_the_database_column_are_rejected():
    long_tags = "\n".join(f"  - {letter * 30}" for letter in "abcde")
    manifest = MANIFEST.replace("tags:\n  - ci\n  - demo", f"tags:\n{long_tags}")

    result = PackageValidator().validate_zip(make_zip(manifest=manifest))

    assert result.valid is False
    assert any(issue.field == "tags" for issue in result.issues)


def test_valid_package_is_stored_as_unpublished_draft(test_app, test_client, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    with test_app.app_context():
        user = UserRepository().create(email="package-valid@example.com", password="secret")
        storage = SimpleNamespace(read=lambda: make_zip({"CHANGELOG.md": "## 1.0.0"}))

        dataset, issues = WorkflowDatasetService().upload_package(storage, user)

        assert issues == []
        assert dataset is not None
        assert dataset.type == "workflow"
        assert dataset.validation_status == "validated"
        assert dataset.package_format == "zip"
        assert dataset.ds_meta_data.dataset_doi is None
        assert dataset.ds_meta_data.title == "demo-workflow"
        assert len(dataset.versions) == 1
        assert len(dataset.files()) == 5
        assert os.path.exists(tmp_path / "uploads" / f"user_{user.id}" / f"dataset_{dataset.id}" / "v1" / "README.md")
        readme = next(file for file in dataset.files() if file.name == "README.md")
        assert os.path.exists(HubfileService().get_path_by_hubfile(readme))


def test_invalid_package_does_not_create_a_dataset(test_app, test_client, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    with test_app.app_context():
        user = UserRepository().create(email="package-invalid@example.com", password="secret")
        before = WorkflowDataset.query.count()
        storage = SimpleNamespace(read=lambda: make_zip(manifest=MANIFEST.replace("license: MIT", "")))

        dataset, issues = WorkflowDatasetService().upload_package(storage, user)

        assert dataset is None
        assert issues
        assert any("license" in issue.message for issue in issues)
        assert WorkflowDataset.query.count() == before


def test_unexpected_persistence_error_hides_internal_details(test_app, test_client, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    with test_app.app_context():
        user = UserRepository().create(email="package-disk@example.com", password="secret")
        before = WorkflowDataset.query.count()

        def fail_makedirs(*args, **kwargs):
            raise OSError("disk full secret")

        monkeypatch.setattr("app.features.workflow.services.os.makedirs", fail_makedirs)
        storage = SimpleNamespace(read=lambda: make_zip())

        dataset, issues = WorkflowDatasetService().upload_package(storage, user)

        assert dataset is None
        assert issues[0].message == "No se pudo guardar el paquete. Revisa los datos e inténtalo de nuevo."
        assert "disk full" not in issues[0].message
        assert WorkflowDataset.query.count() == before


def test_empty_and_corrupt_zip_packages_are_rejected():
    empty_result = PackageValidator().validate_zip(b"")
    corrupt_result = PackageValidator().validate_zip(b"not-a-zip")

    assert empty_result.valid is False
    assert any("vacío" in issue.message for issue in empty_result.issues)
    assert corrupt_result.valid is False
    assert any("ZIP válido" in issue.message for issue in corrupt_result.issues)


def test_package_size_and_file_count_limits_are_enforced(monkeypatch):
    data = make_zip()

    monkeypatch.setattr("app.features.workflow.package.MAX_PACKAGE_BYTES", 10)
    too_big = PackageValidator().validate_zip(data)
    assert too_big.valid is False
    assert any("supera el límite" in issue.message for issue in too_big.issues)

    monkeypatch.setattr("app.features.workflow.package.MAX_PACKAGE_BYTES", 10 * 1024 * 1024)
    monkeypatch.setattr("app.features.workflow.package.MAX_FILES", 2)
    too_many = PackageValidator().validate_zip(data)
    assert too_many.valid is False
    assert any("límite de 2 archivos" in issue.message for issue in too_many.issues)

    monkeypatch.setattr("app.features.workflow.package.MAX_FILES", 100)
    monkeypatch.setattr("app.features.workflow.package.MAX_UNCOMPRESSED_BYTES", 10)
    too_uncompressed = PackageValidator().validate_zip(data)
    assert too_uncompressed.valid is False
    assert any("descomprimido" in issue.message for issue in too_uncompressed.issues)


def test_common_root_folder_and_macos_metadata_are_stripped():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("demo-bundle/actionhub.yaml", MANIFEST)
        archive.writestr("demo-bundle/workflow.yml", WORKFLOW)
        archive.writestr("demo-bundle/README.md", "# Demo\n")
        archive.writestr("demo-bundle/LICENSE", "MIT\n")
        archive.writestr("demo-bundle/.DS_Store", "junk")
        archive.writestr("demo-bundle/__MACOSX/._README.md", "junk")

    result = PackageValidator().validate_zip(buffer.getvalue())

    assert result.valid is True
    assert set(result.files) == {"actionhub.yaml", "workflow.yml", "README.md", "LICENSE"}


def test_duplicate_entries_and_symlinks_in_zip_are_rejected():
    dup_buffer = io.BytesIO()
    with zipfile.ZipFile(dup_buffer, "w") as archive:
        archive.writestr("actionhub.yaml", MANIFEST)
        archive.writestr("workflow.yml", WORKFLOW)
        archive.writestr("README.md", "# First\n")
        archive.writestr("README.md", "# Duplicate\n")
        archive.writestr("LICENSE", "MIT\n")

    dup_result = PackageValidator().validate_zip(dup_buffer.getvalue())
    assert dup_result.valid is False
    assert any("duplicado" in issue.message for issue in dup_result.issues)

    symlink_buffer = io.BytesIO()
    with zipfile.ZipFile(symlink_buffer, "w") as archive:
        archive.writestr("actionhub.yaml", MANIFEST)
        archive.writestr("workflow.yml", WORKFLOW)
        archive.writestr("README.md", "# Demo\n")
        archive.writestr("LICENSE", "MIT\n")
        info = zipfile.ZipInfo("fixtures/link.txt")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "/etc/passwd")

    symlink_result = PackageValidator().validate_zip(symlink_buffer.getvalue())
    assert symlink_result.valid is False
    assert any("enlaces simbólicos" in issue.message for issue in symlink_result.issues)


def test_invalid_text_and_manifest_encodings_or_structures_are_rejected():
    empty_readme = PackageValidator().validate_zip(make_zip({"README.md": "   \n"}))
    assert empty_readme.valid is False
    assert any(issue.file == "README.md" and "vacío" in issue.message for issue in empty_readme.issues)

    non_utf8_readme = PackageValidator().validate_zip(make_zip({"README.md": b"\xff\xfe"}))
    assert non_utf8_readme.valid is False
    assert any(issue.file == "README.md" and "UTF-8" in issue.message for issue in non_utf8_readme.issues)

    non_utf8_manifest = PackageValidator().validate_zip(make_zip(manifest=b"\xff\xfe"))
    assert non_utf8_manifest.valid is False
    assert any(issue.file == "actionhub.yaml" and "UTF-8" in issue.message for issue in non_utf8_manifest.issues)

    dup_manifest = PackageValidator().validate_zip(make_zip(manifest="name: a\nname: b\n"))
    assert dup_manifest.valid is False
    assert any(issue.file == "actionhub.yaml" and "Clave duplicada" in issue.message for issue in dup_manifest.issues)

    list_manifest = PackageValidator().validate_zip(make_zip(manifest="- not\n- a-mapping\n"))
    assert list_manifest.valid is False
    assert any(issue.file == "actionhub.yaml" and "objeto YAML" in issue.message for issue in list_manifest.issues)
