"""Lifecycle of a workflow dataset (#19).

A workflow moves through ``validation_status``::

    draft ──► validated ──► published
      │          ▲  │
      ▼          │  ▼
    failed ──────┘ failed

- ``validated`` requires the blocking validation layers (L1 + L2). L4 (#18)
  will add its security grade on the same transition.
- ``published`` requires ``validated`` and a DOI assigned by Zenodo or
  fakenodo. A published workflow is immutable: it cannot be validated or
  published again (a new version is WI-196).

Any other transition raises ``InvalidTransition``.
"""

import logging

from app import db
from app.features.hubfile.services import HubfileService
from app.features.workflow.models import ValidationStatus, WorkflowDataset

logger = logging.getLogger(__name__)

ALLOWED_TRANSITIONS = {
    ValidationStatus.DRAFT: {ValidationStatus.VALIDATED, ValidationStatus.FAILED},
    ValidationStatus.FAILED: {ValidationStatus.VALIDATED, ValidationStatus.FAILED},
    ValidationStatus.VALIDATED: {ValidationStatus.VALIDATED, ValidationStatus.FAILED, ValidationStatus.PUBLISHED},
    ValidationStatus.PUBLISHED: set(),
}


class InvalidTransition(ValueError):
    """The workflow cannot move from its current status to the requested one."""

    def __init__(self, current: str, target: str):
        super().__init__(f"No se puede pasar de '{current}' a '{target}'.")
        self.current = current
        self.target = target


class PublicationError(RuntimeError):
    """Zenodo/fakenodo did not complete the publication. The workflow stays ``validated``."""


def can_transition(current: str, target: str) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def transition(workflow: WorkflowDataset, target: str) -> None:
    """Move ``workflow`` to ``target`` or raise ``InvalidTransition``. Does not commit."""
    current = workflow.validation_status or ValidationStatus.DRAFT
    if not can_transition(current, target):
        raise InvalidTransition(current, target)
    workflow.validation_status = target


class WorkflowPublicationService:
    """Publish a validated workflow in Zenodo/fakenodo and store its DOI."""

    def __init__(self, zenodo=None, hubfiles=None):
        if zenodo is None:
            # Imported here to avoid a circular import at module load.
            from app.features.zenodo.services import ZenodoService

            zenodo = ZenodoService()
        self.zenodo = zenodo
        self.hubfiles = hubfiles or HubfileService()

    def publish(self, workflow: WorkflowDataset) -> str:
        """Publish ``workflow`` and return its DOI.

        Steps: create the deposition, upload the files of the latest version,
        publish and read the DOI. ``deposition_id`` is stored as soon as the
        deposition exists, so a failed attempt can be traced. If any step
        fails, the workflow stays ``validated`` without DOI and
        ``PublicationError`` is raised.
        """
        if not can_transition(workflow.validation_status, ValidationStatus.PUBLISHED):
            raise InvalidTransition(workflow.validation_status, ValidationStatus.PUBLISHED)
        version = workflow.latest_version()
        if version is None or not version.files:
            raise PublicationError("El workflow no tiene archivos que publicar.")

        metadata = workflow.ds_meta_data
        try:
            deposition = self.zenodo.create_new_deposition(workflow)
            deposition_id = deposition["id"]
            metadata.deposition_id = deposition_id
            db.session.commit()

            for hubfile in version.files:
                self.zenodo.upload_file_from_path(
                    deposition_id,
                    self.hubfiles.get_path_by_hubfile(hubfile),
                    self.deposition_filename(hubfile.name),
                )
            self.zenodo.publish_deposition(deposition_id)
            doi = self.zenodo.get_doi(deposition_id)
            if not doi:
                raise PublicationError("La deposition se publicó sin DOI.")
        except PublicationError:
            db.session.rollback()
            raise
        except Exception as exc:
            db.session.rollback()
            logger.exception("Could not publish workflow %s: %s", workflow.id, exc)
            raise PublicationError("No se pudo publicar el workflow. Inténtalo de nuevo más tarde.") from exc

        metadata.dataset_doi = doi
        transition(workflow, ValidationStatus.PUBLISHED)
        db.session.commit()
        return doi

    @staticmethod
    def deposition_filename(name: str) -> str:
        """Zenodo file keys cannot contain ``/``: ``fixtures/input.txt`` becomes ``fixtures__input.txt``."""
        return name.replace("/", "__")
