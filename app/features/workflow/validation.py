"""L1 and L2 validation for GitHub Actions workflows.

L1 (syntax) and L2 (schema) are blocking: a file that fails either layer
cannot move a workflow to ``validation_status='validated'``.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from jsonschema.validators import validator_for
from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.error import YAMLError

WORKFLOW_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "github-workflow.schema.json"

_TYPE_NAMES_ES = {
    "object": "un objeto",
    "array": "una lista",
    "string": "una cadena de texto",
    "integer": "un número entero",
    "number": "un número",
    "boolean": "un booleano",
    "null": "nulo",
}


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


@lru_cache(maxsize=4)
def _load_workflow_validator(schema_path: Path):
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator_cls = validator_for(schema)
    validator_cls.check_schema(schema)
    return validator_cls(schema)


def _format_schema_error(error) -> str:
    """Translate the most common jsonschema messages into Spanish."""
    validator = error.validator
    if validator == "required":
        prop = error.message.split(" is a required property")[0].strip("'\"")
        return f"falta la propiedad obligatoria '{prop}'"
    if validator == "type":
        expected = error.validator_value
        if isinstance(expected, list):
            labels = ", ".join(_TYPE_NAMES_ES.get(item, item) for item in expected)
            return f"tipo no válido; se esperaba uno de: {labels}"
        return f"tipo no válido; se esperaba {_TYPE_NAMES_ES.get(expected, expected)}"
    if validator == "additionalProperties":
        return (
            error.message.replace("Additional properties are not allowed", "no se permiten propiedades adicionales")
            .replace("was unexpected", "no es válida")
            .replace("were unexpected", "no son válidas")
        )
    if validator == "enum":
        allowed = ", ".join(repr(item) for item in error.validator_value)
        return f"valor no permitido; debe ser uno de: {allowed}"
    if validator == "minProperties":
        return f"debe definir al menos {error.validator_value} propiedad(es)"
    if validator == "minItems":
        return f"debe contener al menos {error.validator_value} elemento(s)"
    if validator in ("anyOf", "oneOf"):
        return "no cumple ninguna de las estructuras válidas del esquema"
    return error.message


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
            return ValidationResult(
                valid=False,
                issues=[ValidationIssue(message=f"No se pudo leer el archivo: {exc}")],
            )
        return self.validate_text(text)

    @staticmethod
    def _invalid(exc: Exception, prefix: str) -> ValidationResult:
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
        line = mark.line + 1 if mark is not None else None
        column = mark.column + 1 if mark is not None else None
        problem = getattr(exc, "problem", None) or str(exc)
        message = f"{prefix}: {problem}"
        return ValidationResult(valid=False, issues=[ValidationIssue(message=message, line=line, column=column)])


class L2Validator:
    """Validate a workflow against the vendored GitHub Actions JSON Schema."""

    def __init__(self, schema_path: str | Path = WORKFLOW_SCHEMA_PATH):
        self._validator = _load_workflow_validator(Path(schema_path).resolve())

    def validate_data(self, data: object) -> ValidationResult:
        if not isinstance(data, dict):
            return ValidationResult(
                valid=False,
                issues=[ValidationIssue(message="Esquema inválido: el workflow debe contener un objeto YAML.")],
            )

        errors = sorted(
            self._validator.iter_errors(data),
            key=lambda item: [str(part) for part in item.absolute_path],
        )
        if not errors:
            return ValidationResult(valid=True, issues=[])

        issues = []
        for error in errors:
            field = ".".join(str(part) for part in error.absolute_path) or None
            issues.append(
                ValidationIssue(
                    message=f"Esquema inválido: {_format_schema_error(error)}",
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
            return ValidationResult(
                valid=False,
                issues=[ValidationIssue(message=f"No se pudo leer el archivo: {exc}")],
            )
        return self.validate_text(text)
