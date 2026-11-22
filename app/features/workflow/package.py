"""Workflow package validation (#14).

A package is a single ``.zip`` with ``actionhub.yaml``, ``workflow.yml``,
``README.md`` and ``LICENSE`` at its root. ``CHANGELOG.md`` and ``fixtures/``
are optional. The zip is inspected before anything is persisted.
"""

import json
import stat
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from jsonschema import Draft202012Validator
from ruamel.yaml import YAML

from app.features.workflow.validation import L1Validator, L2Validator

REQUIRED_FILES = {"actionhub.yaml", "workflow.yml", "README.md", "LICENSE"}
OPTIONAL_FILES = {"CHANGELOG.md"}
ALLOWED_TOP_LEVEL = REQUIRED_FILES | OPTIONAL_FILES | {"fixtures"}
MAX_PACKAGE_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
MAX_FILES = 100
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
SCHEMA_PATH = SCHEMA_DIR / "actionhub.schema.json"


@dataclass(frozen=True)
class PackageIssue:
    message: str
    file: str | None = None
    field: str | None = None
    line: int | None = None


@dataclass
class PackageValidationResult:
    valid: bool
    issues: list[PackageIssue]
    manifest: dict | None = None
    files: dict[str, bytes] = field(default_factory=dict)
    workflow_yaml: str | None = None


class PackageValidator:
    def __init__(self):
        self._schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self._yaml = YAML(typ="safe", pure=True)
        self._yaml.allow_duplicate_keys = False
        self._l2 = L2Validator()

    def validate_zip(self, data: bytes) -> PackageValidationResult:
        issues: list[PackageIssue] = []
        if not data:
            return PackageValidationResult(
                False,
                [PackageIssue("El paquete está vacío.")],
            )
        if len(data) > MAX_PACKAGE_BYTES:
            limit_mb = MAX_PACKAGE_BYTES // (1024 * 1024)
            msg = f"El paquete supera el límite de {limit_mb} MB."
            return PackageValidationResult(False, [PackageIssue(msg)])

        try:
            archive = zipfile.ZipFile(BytesIO(data))
        except zipfile.BadZipFile:
            return PackageValidationResult(
                False,
                [PackageIssue("El archivo no es un ZIP válido.")],
            )

        with archive:
            files = self._extract_files(archive, issues)
            if issues:
                return PackageValidationResult(False, issues)

            missing = REQUIRED_FILES - set(files)
            for name in sorted(missing):
                issues.append(
                    PackageIssue(
                        f"Falta el archivo obligatorio: {name}.",
                        file=name,
                    )
                )
            if issues:
                return PackageValidationResult(False, issues)

            self._validate_text_file(files, "README.md", issues)
            self._validate_text_file(files, "LICENSE", issues)

            manifest = self._validate_manifest(files["actionhub.yaml"], issues)
            workflow_yaml = files["workflow.yml"].decode(
                "utf-8",
                errors="replace",
            )
            self._validate_workflow(workflow_yaml, issues)

            if issues:
                return PackageValidationResult(
                    False,
                    issues,
                    files=files,
                    workflow_yaml=workflow_yaml,
                )
            return PackageValidationResult(
                True,
                [],
                manifest=manifest,
                files=files,
                workflow_yaml=workflow_yaml,
            )

    def _extract_files(
        self,
        archive: zipfile.ZipFile,
        issues: list[PackageIssue],
    ) -> dict[str, bytes]:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) > MAX_FILES:
            msg = f"El paquete supera el límite de {MAX_FILES} archivos."
            issues.append(PackageIssue(msg))
            return {}

        names = [self._normalize_name(info.filename) for info in infos]
        names = self._strip_common_root(names)

        files: dict[str, bytes] = {}
        total_size = 0
        for info, name in zip(infos, names):
            is_macos_meta = name.startswith("__MACOSX/") or name.endswith(".DS_Store")
            if not name or is_macos_meta:
                continue
            if self._unsafe_path(name):
                issues.append(
                    PackageIssue(
                        "Ruta no permitida dentro del ZIP.",
                        file=name,
                    )
                )
                continue
            top = name.split("/", 1)[0]
            if top not in ALLOWED_TOP_LEVEL:
                msg = (
                    f"Archivo no permitido en el paquete: {name}. "
                    "Solo se aceptan actionhub.yaml, workflow.yml, "
                    "README.md, LICENSE, CHANGELOG.md y fixtures/."
                )
                issues.append(PackageIssue(msg, file=name))
                continue
            if len(name) > 120:
                msg = "El nombre del archivo supera los 120 caracteres: " f"{name}."
                issues.append(PackageIssue(msg, file=name))
                continue
            if name in files:
                issues.append(PackageIssue("Archivo duplicado en el ZIP.", file=name))
                continue
            if stat.S_ISLNK(info.external_attr >> 16):
                issues.append(
                    PackageIssue(
                        "No se permiten enlaces simbólicos en el ZIP.",
                        file=name,
                    )
                )
                continue
            total_size += info.file_size
            if total_size > MAX_UNCOMPRESSED_BYTES:
                limit_mb = MAX_UNCOMPRESSED_BYTES // (1024 * 1024)
                msg = "El contenido descomprimido supera el límite de " f"{limit_mb} MB."
                issues.append(PackageIssue(msg))
                return {}
            try:
                files[name] = archive.read(info)
            except Exception as exc:  # pragma: no cover
                issues.append(
                    PackageIssue(
                        f"No se pudo leer el archivo: {exc}.",
                        file=name,
                    )
                )
        return files

    @staticmethod
    def _normalize_name(name: str) -> str:
        return name.replace("\\", "/").lstrip("/")

    @staticmethod
    def _strip_common_root(names: list[str]) -> list[str]:
        non_empty = [name for name in names if name]
        roots = {name.split("/", 1)[0] for name in non_empty}
        if len(roots) != 1:
            return names
        root = next(iter(roots))
        prefix = root + "/"
        matches_root = all(name == root or name.startswith(prefix) for name in non_empty)
        if not matches_root:
            return names
        if root in REQUIRED_FILES:
            return names
        prefix_len = len(prefix)
        return [name[prefix_len:] if name.startswith(prefix) else name for name in names]

    @staticmethod
    def _unsafe_path(name: str) -> bool:
        parts = name.split("/")
        has_drive = len(parts[0]) == 2 and parts[0][1] == ":"
        return name.startswith("/") or ".." in parts or has_drive

    @staticmethod
    def _validate_text_file(
        files: dict[str, bytes],
        name: str,
        issues: list[PackageIssue],
    ) -> None:
        try:
            content = files[name].decode("utf-8")
        except UnicodeDecodeError:
            issues.append(PackageIssue("El archivo debe estar en UTF-8.", file=name))
            return
        if not content.strip():
            issues.append(PackageIssue("El archivo no puede estar vacío.", file=name))

    def _validate_manifest(
        self,
        data: bytes,
        issues: list[PackageIssue],
    ) -> dict | None:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            issues.append(
                PackageIssue(
                    "El manifiesto debe estar en UTF-8.",
                    file="actionhub.yaml",
                )
            )
            return None

        l1 = L1Validator().validate_text(text)
        for issue in l1.issues:
            issues.append(
                PackageIssue(
                    issue.message,
                    file="actionhub.yaml",
                    line=issue.line,
                )
            )
        if not l1.valid:
            return None

        try:
            manifest = self._yaml.load(text)
        except Exception as exc:  # pragma: no cover
            issues.append(
                PackageIssue(
                    f"No se pudo leer actionhub.yaml: {exc}.",
                    file="actionhub.yaml",
                )
            )
            return None
        if not isinstance(manifest, dict):
            issues.append(
                PackageIssue(
                    "actionhub.yaml debe contener un objeto YAML.",
                    file="actionhub.yaml",
                )
            )
            return None

        validator = Draft202012Validator(self._schema)
        errors = sorted(
            validator.iter_errors(manifest),
            key=lambda item: [str(part) for part in item.absolute_path],
        )
        for error in errors:
            path_parts = [str(part) for part in error.absolute_path]
            field_name = ".".join(path_parts) or None
            issues.append(
                PackageIssue(
                    f"Manifiesto inválido: {error.message}",
                    file="actionhub.yaml",
                    field=field_name,
                )
            )
        tags = manifest.get("tags") or []
        if tags and len(", ".join(tags)) > 120:
            msg = "La suma de los tags supera los 120 caracteres " "de la columna."
            issues.append(PackageIssue(msg, file="actionhub.yaml", field="tags"))
        return manifest

    def _validate_workflow(
        self,
        text: str,
        issues: list[PackageIssue],
    ) -> None:
        l1 = L1Validator().validate_text(text)
        for issue in l1.issues:
            issues.append(
                PackageIssue(
                    issue.message,
                    file="workflow.yml",
                    line=issue.line,
                )
            )
        if not l1.valid:
            return

        try:
            workflow = self._yaml.load(text)
        except Exception as exc:  # pragma: no cover
            issues.append(
                PackageIssue(
                    f"No se pudo leer workflow.yml: {exc}.",
                    file="workflow.yml",
                )
            )
            return

        l2 = self._l2.validate_data(workflow)
        for issue in l2.issues:
            issues.append(
                PackageIssue(
                    issue.message,
                    file="workflow.yml",
                    field=issue.field,
                    line=issue.line,
                )
            )
