"""Extract comparable metadata from a GitHub Actions workflow.

The metadata answers "what does this workflow do?" without downloading it:
which events trigger it (``on``), which jobs it has, where they run
(``runs-on``) and which actions or reusable workflows they use (``uses``).

Extraction runs after L1, so the text is expected to be well-formed YAML.
"""

import json
import re
from dataclasses import asdict, dataclass, field

from ruamel.yaml import YAML

MATRIX_EXPRESSION = re.compile(r"^\$\{\{\s*matrix\.([A-Za-z_][\w-]*)\s*\}\}$")


class MetadataError(ValueError):
    """The text cannot be read as a workflow mapping."""


@dataclass(frozen=True)
class JobMetadata:
    id: str
    name: str | None = None
    runs_on: list[str] = field(default_factory=list)
    uses: str | None = None
    matrix: dict[str, list] = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WorkflowMetadata:
    name: str | None
    triggers: list[str]
    jobs: list[JobMetadata]
    runners: list[str]
    actions: list[str]
    reusable_workflows: list[str]

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, default=str)


class WorkflowMetadataExtractor:
    """Read triggers, jobs, runners and used actions from a workflow."""

    def extract_text(self, text: str) -> WorkflowMetadata:
        yaml = YAML(typ="safe", pure=True)
        document = yaml.load(text)
        if not isinstance(document, dict):
            raise MetadataError("El workflow no es un mapa YAML")
        return self.extract(document)

    def extract(self, document: dict) -> WorkflowMetadata:
        jobs = [self._job(job_id, body) for job_id, body in self._mapping(document.get("jobs")).items()]
        return WorkflowMetadata(
            name=self._text(document.get("name")),
            triggers=self._triggers(self._on(document)),
            jobs=jobs,
            runners=_unique(runner for job in jobs for runner in job.runs_on),
            actions=_unique(action for job in jobs for action in job.actions),
            reusable_workflows=_unique(job.uses for job in jobs if job.uses),
        )

    @staticmethod
    def _on(document: dict):
        # A YAML 1.1 loader reads the bare key ``on`` as the boolean ``True``.
        if "on" in document:
            return document["on"]
        return document.get(True)

    @staticmethod
    def _triggers(on) -> list[str]:
        if isinstance(on, str):
            return [on]
        if isinstance(on, list):
            return _unique(str(event) for event in on if event is not None)
        if isinstance(on, dict):
            return _unique(str(event) for event in on)
        return []

    def _job(self, job_id, body) -> JobMetadata:
        body = self._mapping(body)
        matrix = self._matrix(body.get("strategy"))
        steps = body.get("steps") if isinstance(body.get("steps"), list) else []
        return JobMetadata(
            id=str(job_id),
            name=self._text(body.get("name")),
            runs_on=self._runs_on(body.get("runs-on"), matrix),
            uses=self._text(body.get("uses")),
            matrix={key: values for key, values in matrix.items() if key not in ("include", "exclude")},
            actions=_unique(step["uses"] for step in steps if isinstance(step, dict) and step.get("uses")),
        )

    def _matrix(self, strategy) -> dict:
        matrix = self._mapping(strategy).get("matrix")
        return matrix if isinstance(matrix, dict) else {}

    def _runs_on(self, runs_on, matrix: dict) -> list[str]:
        if isinstance(runs_on, dict):
            labels = runs_on.get("labels")
            values = [runs_on["group"]] if runs_on.get("group") else []
            values += labels if isinstance(labels, list) else [labels] if labels else []
        elif isinstance(runs_on, list):
            values = runs_on
        elif runs_on is None:
            values = []
        else:
            values = [runs_on]

        runners = []
        for value in values:
            runners.extend(self._expand(str(value), matrix))
        return _unique(runners)

    @staticmethod
    def _expand(value: str, matrix: dict) -> list[str]:
        """Resolve ``${{ matrix.<key> }}`` to the values the matrix declares."""
        match = MATRIX_EXPRESSION.match(value.strip())
        if not match:
            return [value]
        key = match.group(1)
        axis = matrix.get(key)
        values = list(axis) if isinstance(axis, list) else []
        for entry in matrix.get("include") or []:
            if isinstance(entry, dict) and key in entry:
                values.append(entry[key])
        flat = []
        for item in values:
            flat.extend(item if isinstance(item, list) else [item])
        return [str(item) for item in flat] or [value]

    @staticmethod
    def _mapping(value) -> dict:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _text(value) -> str | None:
        return str(value) if value is not None else None


def _unique(values) -> list:
    """Keep the first occurrence of each value, in order."""
    return list(dict.fromkeys(values))
