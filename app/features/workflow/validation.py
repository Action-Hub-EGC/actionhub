"""L1 and L2 validation for GitHub Actions workflows.

L1 (syntax) and L2 (schema) are blocking: a file that fails either layer
cannot move a workflow to ``validation_status='validated'``.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from jsonschema.validators import validator_for
from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.error import YAMLError

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
WORKFLOW_SCHEMA_PATH = SCHEMA_DIR / "github-workflow.schema.json"


@dataclass(frozen=True)
class ValidationIssue:
    message: str
    line: int | None = None
    column: int | None = None
    field: str | None = None


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    issues: list[ValidationIssue]


class L1Validator:
    """Validate YAML syntax with line and column information."""

    def validate_text(self, text: str) -> ValidationResult:
        yaml = YAML(typ="safe", pure=True)
        yaml.allow_duplicate_keys = False
        try:
            yaml.load(text)
        except DuplicateKeyError as exc:
            return self._invalid(exc, prefix="Clave duplicada")
        except YAMLError as exc:
            return self._invalid(exc, prefix="YAML inválido")
        return ValidationResult(valid=True, issues=[])

    def validate_file(self, path: str | Path) -> ValidationResult:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            msg = f"No se pudo leer el archivo: {exc}"
            return ValidationResult(
                valid=False,
                issues=[ValidationIssue(message=msg)],
            )
        return self.validate_text(text)

    @staticmethod
    def _invalid(exc: Exception, prefix: str) -> ValidationResult:
        mark = getattr(exc, "problem_mark", None)
        if mark is None:
            mark = getattr(exc, "context_mark", None)
        line = mark.line + 1 if mark is not None else None
        column = mark.column + 1 if mark is not None else None
        problem = getattr(exc, "problem", None) or str(exc)
        message = f"{prefix}: {problem}"
        issue = ValidationIssue(message=message, line=line, column=column)
        return ValidationResult(valid=False, issues=[issue])


class L2Validator:
    """Validate a workflow against the vendored GitHub Actions JSON Schema."""

    def __init__(self, schema_path: str | Path = WORKFLOW_SCHEMA_PATH):
        raw = Path(schema_path).read_text(encoding="utf-8")
        self._schema = json.loads(raw)
        validator_cls = validator_for(self._schema)
        validator_cls.check_schema(self._schema)
        self._validator = validator_cls(self._schema)

    def validate_data(self, data: object) -> ValidationResult:
        if not isinstance(data, dict):
            msg = (
                "Esquema inválido: el workflow debe contener "
                "un objeto YAML."
            )
            return ValidationResult(
                valid=False,
                issues=[ValidationIssue(message=msg)],
            )

        errors = sorted(
            self._validator.iter_errors(data),
            key=lambda item: [str(part) for part in item.absolute_path],
        )
        if not errors:
            return ValidationResult(valid=True, issues=[])

        issues = []
        for error in errors:
            path_parts = [str(part) for part in error.absolute_path]
            field = ".".join(path_parts) or None
            issues.append(
                ValidationIssue(
                    message=f"Esquema inválido: {error.message}",
                    field=field,
                )
            )
        return ValidationResult(valid=False, issues=issues)

    def validate_text(self, text: str) -> ValidationResult:
        l1 = L1Validator().validate_text(text)
        if not l1.valid:
            return l1

        yaml = YAML(typ="safe", pure=True)
        yaml.allow_duplicate_keys = False
        data = yaml.load(text)
        return self.validate_data(data)

    def validate_file(self, path: str | Path) -> ValidationResult:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            msg = f"No se pudo leer el archivo: {exc}"
            return ValidationResult(
                valid=False,
                issues=[ValidationIssue(message=msg)],
            )
        return self.validate_text(text)
