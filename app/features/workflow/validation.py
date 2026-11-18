"""L1 validation: well-formed YAML and no duplicate keys.

L1 is blocking: a file that fails here cannot move a workflow to
``validation_status='validated'``.
"""

from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.error import YAMLError


@dataclass(frozen=True)
class ValidationIssue:
    message: str
    line: int | None = None
    column: int | None = None


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
