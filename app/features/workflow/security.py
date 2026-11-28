"""L4 security rules and A-F grading for GitHub Actions workflows (#18).

L4 is non-blocking: a workflow with a grade below C (D, E or F) can still be
validated and published, but ActionHub displays a security warning.
"""

import re
from dataclasses import dataclass

from ruamel.yaml import YAML

FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
DOCKER_DIGEST_RE = re.compile(r"@sha256:[0-9a-fA-F]{64}$")
HEAD_REF_RE = re.compile(
    r"github\.event\.pull_request\.head\b|github\.head_ref\b|refs/pull/[^/\s]+/(?:head|merge)\b",
    re.IGNORECASE,
)

SEC01_PENALTY = 15
SEC01_MAX_PENALTY = 45
SEC02_PENALTY = 10
SEC03_PENALTY = 10
SEC04_PENALTY = 25

GRADE_BANDS = (
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
    (50, "E"),
    (0, "F"),
)
WARNING_GRADES = frozenset({"D", "E", "F"})


class SecurityEvaluationError(ValueError):
    """The workflow text could not be parsed as a YAML mapping."""


@dataclass(frozen=True)
class SecurityFinding:
    rule_id: str
    penalty: int
    message: str
    location: str | None = None


@dataclass(frozen=True)
class SecurityReport:
    score: int
    grade: str
    findings: list[SecurityFinding]

    @property
    def has_warning(self) -> bool:
        return has_security_warning(self.grade)

    @property
    def warning_message(self) -> str | None:
        if not self.has_warning:
            return None
        return (
            f"Advertencia de seguridad: este workflow tiene calificación {self.grade} "
            f"({self.score}/100). Revisa las incidencias detectadas antes de usarlo."
        )


def grade_for_score(score: int) -> str:
    """Map a numeric security score (0-100) to its A-F grade."""
    clamped = max(0, min(100, int(score)))
    for minimum, grade in GRADE_BANDS:
        if clamped >= minimum:
            return grade
    return "F"


def has_security_warning(grade: str | None) -> bool:
    """Return True when the security grade is below C (D, E or F)."""
    return grade in WARNING_GRADES


class L4SecurityEvaluator:
    """Evaluate L4 security rules (SEC-01 to SEC-04) on a workflow."""

    def evaluate_text(self, text: str) -> SecurityReport:
        yaml = YAML(typ="safe", pure=True)
        document = yaml.load(text)
        if not isinstance(document, dict):
            raise SecurityEvaluationError("El workflow no es un mapa YAML.")
        return self.evaluate(document)

    def evaluate(self, document: dict) -> SecurityReport:
        jobs = self._mapping(document.get("jobs"))
        findings: list[SecurityFinding] = []
        findings.extend(self._check_sec01(jobs))
        findings.extend(self._check_sec02(document, jobs))
        findings.extend(self._check_sec03(document, jobs))
        findings.extend(self._check_sec04(document, jobs))

        total_penalty = sum(finding.penalty for finding in findings)
        score = max(0, 100 - total_penalty)
        return SecurityReport(score=score, grade=grade_for_score(score), findings=findings)

    def _check_sec01(self, jobs: dict) -> list[SecurityFinding]:
        """SEC-01: pin every external action by full SHA (-15 each, max -45)."""
        references: list[tuple[str, str]] = []
        for job_id, raw_body in jobs.items():
            body = self._mapping(raw_body)
            job_uses = body.get("uses")
            if isinstance(job_uses, str) and job_uses.strip():
                references.append((f"jobs.{job_id}.uses", job_uses.strip()))

            steps = body.get("steps") if isinstance(body.get("steps"), list) else []
            for index, step in enumerate(steps, start=1):
                if not isinstance(step, dict):
                    continue
                step_uses = step.get("uses")
                if isinstance(step_uses, str) and step_uses.strip():
                    references.append((f"jobs.{job_id}.steps[{index}].uses", step_uses.strip()))

        findings: list[SecurityFinding] = []
        seen_unpinned: set[str] = set()
        applied_total = 0

        for location, ref in references:
            if ref.startswith("./") or self._is_pinned(ref) or ref in seen_unpinned:
                continue
            seen_unpinned.add(ref)
            penalty = min(SEC01_PENALTY, SEC01_MAX_PENALTY - applied_total)
            applied_total += penalty
            findings.append(
                SecurityFinding(
                    rule_id="SEC-01",
                    penalty=penalty,
                    message=f"La acción externa '{ref}' no está fijada por SHA completo.",
                    location=location,
                )
            )
        return findings

    def _check_sec02(self, document: dict, jobs: dict) -> list[SecurityFinding]:
        """SEC-02: declare permissions (-10, once per workflow)."""
        if self._has_permissions(document):
            return []
        if jobs and all(self._has_permissions(self._mapping(body)) for body in jobs.values()):
            return []
        return [
            SecurityFinding(
                rule_id="SEC-02",
                penalty=SEC02_PENALTY,
                message="El workflow no declara un bloque 'permissions' explícito.",
                location="permissions",
            )
        ]

    def _check_sec03(self, document: dict, jobs: dict) -> list[SecurityFinding]:
        """SEC-03: do not use write-all (-10, once per workflow)."""
        if self._is_write_all(document.get("permissions")):
            return [
                SecurityFinding(
                    rule_id="SEC-03",
                    penalty=SEC03_PENALTY,
                    message="No uses 'permissions: write-all'; concede solo los permisos mínimos necesarios.",
                    location="permissions",
                )
            ]
        for job_id, raw_body in jobs.items():
            body = self._mapping(raw_body)
            if self._is_write_all(body.get("permissions")):
                return [
                    SecurityFinding(
                        rule_id="SEC-03",
                        penalty=SEC03_PENALTY,
                        message="No uses 'permissions: write-all'; concede solo los permisos mínimos necesarios.",
                        location=f"jobs.{job_id}.permissions",
                    )
                ]
        return []

    def _check_sec04(self, document: dict, jobs: dict) -> list[SecurityFinding]:
        """SEC-04: do not combine pull_request_target with checkout of the head (-25 each)."""
        if "pull_request_target" not in self._triggers(document):
            return []

        findings: list[SecurityFinding] = []
        for job_id, raw_body in jobs.items():
            body = self._mapping(raw_body)
            steps = body.get("steps") if isinstance(body.get("steps"), list) else []
            for index, step in enumerate(steps, start=1):
                if not isinstance(step, dict):
                    continue
                if self._is_head_checkout(step):
                    findings.append(
                        SecurityFinding(
                            rule_id="SEC-04",
                            penalty=SEC04_PENALTY,
                            message=(
                                "Combinación peligrosa: 'pull_request_target' con checkout del código del head "
                                "del pull request."
                            ),
                            location=f"jobs.{job_id}.steps[{index}]",
                        )
                    )
        return findings

    @staticmethod
    def _is_pinned(ref: str) -> bool:
        if ref.startswith("docker://"):
            return bool(DOCKER_DIGEST_RE.search(ref))
        _, separator, version = ref.rpartition("@")
        return bool(separator and FULL_SHA_RE.fullmatch(version.strip()))

    @staticmethod
    def _has_permissions(mapping: dict) -> bool:
        return "permissions" in mapping and mapping["permissions"] is not None

    @staticmethod
    def _is_write_all(permissions) -> bool:
        return isinstance(permissions, str) and permissions.strip().lower() == "write-all"

    @staticmethod
    def _triggers(document: dict) -> set[str]:
        raw_on = document["on"] if "on" in document else document.get(True)
        if isinstance(raw_on, str):
            return {raw_on}
        if isinstance(raw_on, list):
            return {str(event) for event in raw_on if event is not None}
        if isinstance(raw_on, dict):
            return {str(event) for event in raw_on}
        return set()

    @staticmethod
    def _is_head_checkout(step: dict) -> bool:
        uses = step.get("uses")
        if not isinstance(uses, str):
            return False
        normalized = uses.strip().lower()
        if not (normalized == "actions/checkout" or normalized.startswith("actions/checkout@")):
            return False
        with_block = step.get("with")
        if not isinstance(with_block, dict):
            return False
        ref = with_block.get("ref")
        return isinstance(ref, str) and bool(HEAD_REF_RE.search(ref))

    @staticmethod
    def _mapping(value) -> dict:
        return value if isinstance(value, dict) else {}
