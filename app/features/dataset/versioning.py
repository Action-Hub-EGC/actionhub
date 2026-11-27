"""New major version of a published dataset (#38, WI-196).

The flow mirrors Zenodo and works for every dataset type through
``BaseDataset``:

1. ``start``: open a local draft ``v<n+1>`` that copies the files and the
   type-specific content (feature models or the workflow version) of the latest
   published version. Nothing is sent to Zenodo yet, so editing a draft works
   offline and never touches the published version.
2. ``add_file``, ``replace_file`` and ``remove_file`` change the draft only.
   A published version is immutable.
3. ``publish``: validate the draft (UVL syntax, or L1 + L2 and the package
   rules for workflows), call ``actions/newversion`` on the previous deposition,
   mirror the draft files on the new deposition, publish it and store the new
   DOI. The concept DOI is shared by every version.

If publishing fails the draft stays a draft and keeps its ``deposition_id``,
so ``publish`` can simply be called again. The previous version keeps its
files, its deposition and its DOI.
"""

import io
import json
import logging
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import PurePosixPath

from app import db
from app.features.dataset.models import Author, BaseDataset, DatasetVersion, PublicationType
from app.features.dataset.services import calculate_checksum_and_size
from app.features.hubfile.models import Hubfile
from app.features.hubfile.services import HubfileService

logger = logging.getLogger(__name__)


class VersionError(ValueError):
    """The requested change is not allowed. The message is shown to the user."""

    def __init__(self, message: str, issues=None):
        super().__init__(message)
        self.issues = list(issues or [])


class VersionPublicationError(RuntimeError):
    """Zenodo/fakenodo did not complete the publication. The draft can be published again."""


class NewVersionService:
    """Create, edit and publish the next major version of a dataset."""

    def __init__(self, zenodo=None, hubfiles=None):
        self._zenodo = zenodo
        self.hubfiles = hubfiles or HubfileService()

    @property
    def zenodo(self):
        if self._zenodo is None:
            # Imported lazily to avoid a circular import at module load.
            from app.features.zenodo.services import ZenodoService

            self._zenodo = ZenodoService()
        return self._zenodo

    # ── Draft ───────────────────────────────────────────────────────────

    def draft_for(self, dataset: BaseDataset):
        """The unpublished version after the latest published one, if any."""
        latest = dataset.latest_dataset_version()
        if latest is not None and not latest.is_published() and dataset.latest_published_dataset_version():
            return latest
        return None

    def start(self, dataset: BaseDataset, change_note: str | None = None) -> DatasetVersion:
        """Open the draft of the next major version, or return the open one.

        A dataset has at most one draft (design §5.1), as Zenodo has at most
        one draft per concept.
        """
        previous = dataset.latest_published_dataset_version()
        if previous is None:
            raise VersionError("Solo se puede crear una versión nueva de un dataset publicado.")
        existing = self.draft_for(dataset)
        if existing is not None:
            return existing

        draft = DatasetVersion(
            dataset_id=dataset.id,
            number=dataset.latest_dataset_version().number + 1,
            change_note=change_note,
            created_at=datetime.utcnow(),
        )
        destination = self.hubfiles.version_directory(dataset, draft)
        try:
            db.session.add(draft)
            db.session.flush()
            if dataset.type == "workflow":
                self._copy_workflow_content(dataset, previous, draft, destination)
            else:
                self._copy_feature_models(dataset, previous, draft, destination)
            db.session.commit()
        except Exception:
            db.session.rollback()
            shutil.rmtree(destination, ignore_errors=True)
            raise
        logger.info("Dataset %s: draft v%s opened from v%s", dataset.id, draft.number, previous.number)
        return draft

    def discard(self, version: DatasetVersion) -> None:
        """Delete a draft and its folder. Its Zenodo draft, if any, is deleted too."""
        self._require_draft(version)
        dataset = version.dataset
        if version.deposition_id:
            try:
                self.zenodo.delete_deposition(version.deposition_id)
            except Exception as exc:  # The local draft goes away anyway.
                logger.warning("Could not delete draft deposition %s: %s", version.deposition_id, exc)
        directory = self.hubfiles.version_directory(dataset, version)
        content = version.workflow_version or None
        if content is not None:
            db.session.delete(content)
        for feature_model in list(version.feature_models):
            db.session.delete(feature_model)
        db.session.delete(version)
        db.session.commit()
        shutil.rmtree(directory, ignore_errors=True)

    # ── File changes ────────────────────────────────────────────────────

    def add_file(self, version: DatasetVersion, name: str, content: bytes, **fm_metadata) -> Hubfile:
        """Add ``name`` to the draft. UVL files become a new feature model."""
        self._require_draft(version)
        name = self._clean_name(version, name)
        if self._find_file(version, name) is not None:
            raise VersionError(f"El archivo {name} ya existe en esta versión. Usa reemplazar.")

        path = self._write(version, name, content)
        try:
            checksum, size = calculate_checksum_and_size(path)
            if version.workflow_version is not None:
                hubfile = Hubfile(name=name, checksum=checksum, size=size)
                version.workflow_version.files.append(hubfile)
                db.session.flush()
                self._sync_workflow_text(version)
            else:
                self._check_uvl(path, name)
                hubfile = self._new_feature_model(version, name, checksum, size, fm_metadata)
            db.session.commit()
        except Exception:
            db.session.rollback()
            os.remove(path)
            raise
        return hubfile

    def replace_file(self, version: DatasetVersion, name: str, content: bytes) -> Hubfile:
        """Overwrite ``name`` in the draft, keeping its metadata."""
        self._require_draft(version)
        name = self._clean_name(version, name)
        hubfile = self._find_file(version, name)
        if hubfile is None:
            raise VersionError(f"El archivo {name} no existe en esta versión.")

        path = self.hubfiles.get_path_by_hubfile(hubfile)
        backup = open(path, "rb").read() if os.path.exists(path) else None
        self._write(version, name, content)
        try:
            if version.workflow_version is None:
                self._check_uvl(path, name)
            hubfile.checksum, hubfile.size = calculate_checksum_and_size(path)
            self._sync_workflow_text(version)
            db.session.commit()
        except Exception:
            db.session.rollback()
            if backup is not None:
                with open(path, "wb") as handle:
                    handle.write(backup)
            raise
        return hubfile

    def remove_file(self, version: DatasetVersion, name: str) -> None:
        """Remove ``name`` from the draft. Required workflow files can only be replaced."""
        self._require_draft(version)
        name = self._clean_name(version, name)
        hubfile = self._find_file(version, name)
        if hubfile is None:
            raise VersionError(f"El archivo {name} no existe en esta versión.")

        if version.workflow_version is not None:
            from app.features.workflow.package import REQUIRED_FILES

            if name in REQUIRED_FILES:
                raise VersionError(f"{name} es obligatorio en un paquete de workflow: reemplázalo en vez de quitarlo.")
            path = self.hubfiles.get_path_by_hubfile(hubfile)
            version.workflow_version.files.remove(hubfile)
            db.session.delete(hubfile)
        else:
            if len(version.feature_models) == 1:
                raise VersionError("La versión debe conservar al menos un modelo UVL.")
            path = self.hubfiles.get_path_by_hubfile(hubfile)
            db.session.delete(hubfile.feature_model)
        db.session.commit()
        if os.path.exists(path):
            os.remove(path)

    # ── Publication ─────────────────────────────────────────────────────

    def publish(self, version: DatasetVersion) -> str:
        """Validate and publish the draft as the new major version. Returns its DOI."""
        self._require_draft(version)
        dataset = version.dataset
        previous = self._previous_published(version)
        if previous is None or not previous.deposition_id:
            raise VersionError("La versión anterior no tiene una deposition publicada en Zenodo.")

        files = version.files()
        if not files:
            raise VersionError("La versión no tiene archivos que publicar.")
        if sorted(file.checksum for file in files) == sorted(file.checksum for file in previous.files()):
            raise VersionError("La versión nueva no cambia ningún archivo respecto a la anterior.")
        if version.workflow_version is not None:
            self._validate_workflow(version)

        try:
            if not version.deposition_id:
                version.deposition_id = self.zenodo.new_version(previous.deposition_id)
                # Stored before uploading: a retry reuses the same Zenodo draft.
                db.session.commit()
            deposition_id = version.deposition_id

            published = self._already_published(deposition_id)
            if published is None:
                self._mirror_files(deposition_id, files)
                self.zenodo.publish_deposition(deposition_id)
                published = self.zenodo.get_deposition(deposition_id)
            doi = published.get("doi")
            if not doi:
                raise VersionPublicationError("La deposition se publicó sin DOI.")
        except VersionPublicationError:
            db.session.rollback()
            raise
        except Exception as exc:
            db.session.rollback()
            logger.exception("Could not publish v%s of dataset %s: %s", version.number, dataset.id, exc)
            message = "No se pudo publicar la versión nueva. Inténtalo de nuevo más tarde."
            raise VersionPublicationError(message) from exc

        version.doi = doi
        version.published_at = datetime.utcnow()
        # ``DSMetaData`` mirrors the latest published version (design §5.1).
        metadata = dataset.ds_meta_data
        metadata.deposition_id = deposition_id
        metadata.dataset_doi = doi
        metadata.conceptrecid = metadata.conceptrecid or published.get("conceptrecid")
        metadata.concept_doi = metadata.concept_doi or published.get("conceptdoi")
        if version.workflow_version is not None:
            dataset.manifest_json = version.workflow_version.manifest_json
            # L4 (#18) is not implemented yet. The grade of the previous
            # version would describe another YAML, so it is cleared, but only
            # once the new version is really the published one. When the L4
            # grader exists, it is called here instead.
            dataset.grade = None
            dataset.security_score = None
        db.session.commit()
        logger.info("Dataset %s: v%s published with DOI %s", dataset.id, version.number, doi)
        return doi

    def _already_published(self, deposition_id: int):
        """The deposition, if an earlier attempt already published it; else ``None``.

        Zenodo can publish and then fail to answer (for example on
        ``get_deposition``). A published deposition cannot take file changes,
        so a retry must only read its DOI instead of mirroring files again.
        """
        deposition = self.zenodo.get_deposition(deposition_id)
        if deposition.get("state") == "done" and deposition.get("doi"):
            return deposition
        return None

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _require_draft(version: DatasetVersion) -> None:
        if version.is_published():
            raise VersionError(f"La versión {version.number} ya está publicada y no se puede cambiar.")

    @staticmethod
    def _previous_published(version: DatasetVersion):
        published = [other for other in version.dataset.dataset_versions if other.doi and other.number < version.number]
        return published[-1] if published else None

    @staticmethod
    def _clean_name(version: DatasetVersion, name: str) -> str:
        """Relative POSIX path inside the version folder, refusing anything that escapes it."""
        raw = (name or "").replace("\\", "/").strip()
        path = PurePosixPath(raw)
        if not raw or path.is_absolute() or ".." in path.parts or raw.endswith("/"):
            raise VersionError("Nombre de archivo no válido.")
        if version.workflow_version is None and (len(path.parts) != 1 or path.suffix != ".uvl"):
            raise VersionError("En un dataset UVL solo se admiten archivos .uvl en la raíz.")
        return str(path)

    @staticmethod
    def _find_file(version: DatasetVersion, name: str):
        return next((file for file in version.files() if file.name == name), None)

    def _write(self, version: DatasetVersion, name: str, content: bytes) -> str:
        path = os.path.join(self.hubfiles.version_directory(version.dataset, version), name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    @staticmethod
    def _check_uvl(path: str, name: str) -> None:
        from app.features.flamapy.services import FlamapyService

        try:
            errors = FlamapyService().validate_uvl_path(path)
        except (UnicodeDecodeError, OSError):
            errors = ["El archivo no es texto UTF-8."]
        if errors:
            raise VersionError(f"{name} no es un modelo UVL válido.", issues=errors)

    def _copy_file(self, dataset, source_version, target_dir, hubfile) -> Hubfile:
        source = os.path.join(self.hubfiles.read_directory(dataset, source_version), hubfile.name)
        target = os.path.join(target_dir, hubfile.name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
        return Hubfile(name=hubfile.name, checksum=hubfile.checksum, size=hubfile.size)

    def _copy_feature_models(self, dataset, previous, draft, destination) -> None:
        from app.features.featuremodel.models import FeatureModel, FMMetaData

        for feature_model in previous.feature_models:
            source_meta = feature_model.fm_meta_data
            meta = FMMetaData(
                uvl_filename=source_meta.uvl_filename,
                title=source_meta.title,
                description=source_meta.description,
                publication_type=source_meta.publication_type,
                publication_doi=source_meta.publication_doi,
                tags=source_meta.tags,
                uvl_version=source_meta.uvl_version,
                fm_metrics_id=source_meta.fm_metrics_id,
            )
            meta.authors = [
                Author(name=author.name, affiliation=author.affiliation, orcid=author.orcid)
                for author in source_meta.authors
            ]
            copy = FeatureModel(data_set_id=dataset.id, dataset_version_id=draft.id, fm_meta_data=meta)
            copy.files = [self._copy_file(dataset, previous, destination, file) for file in feature_model.files]
            db.session.add(copy)
        db.session.flush()

    def _copy_workflow_content(self, dataset, previous, draft, destination) -> None:
        from app.features.workflow.models import WorkflowVersion

        source = previous.workflow_version
        if source is None:
            raise VersionError("La versión anterior no tiene contenido de workflow.")
        copy = WorkflowVersion(
            workflow_dataset_id=dataset.id,
            dataset_version_id=draft.id,
            manifest_json=source.manifest_json,
            workflow_yaml=source.workflow_yaml,
            metadata_json=source.metadata_json,
            created_at=datetime.utcnow(),
        )
        copy.files = [self._copy_file(dataset, previous, destination, file) for file in source.files]
        db.session.add(copy)
        db.session.flush()

    def _new_feature_model(self, version, name, checksum, size, fm_metadata) -> Hubfile:
        from app.features.featuremodel.models import FeatureModel, FMMetaData

        publication_type = fm_metadata.get("publication_type", PublicationType.NONE)
        if isinstance(publication_type, str):
            publication_type = PublicationType[publication_type]
        meta = FMMetaData(
            uvl_filename=name,
            title=fm_metadata.get("title") or PurePosixPath(name).stem,
            description=fm_metadata.get("description") or "",
            publication_type=publication_type,
            publication_doi=fm_metadata.get("publication_doi"),
            tags=fm_metadata.get("tags"),
            uvl_version=fm_metadata.get("uvl_version"),
        )
        hubfile = Hubfile(name=name, checksum=checksum, size=size)
        feature_model = FeatureModel(
            data_set_id=version.dataset_id,
            dataset_version_id=version.id,
            fm_meta_data=meta,
            files=[hubfile],
        )
        db.session.add(feature_model)
        db.session.flush()
        return hubfile

    def _read_files(self, version) -> dict[str, bytes]:
        contents = {}
        for hubfile in version.files():
            with open(self.hubfiles.get_path_by_hubfile(hubfile), "rb") as handle:
                contents[hubfile.name] = handle.read()
        return contents

    def _sync_workflow_text(self, version) -> None:
        """Keep the draft's manifest and YAML columns in step with its files."""
        content = version.workflow_version
        if content is None:
            return
        files = self._read_files(version)
        if "workflow.yml" in files:
            content.workflow_yaml = files["workflow.yml"].decode("utf-8", errors="replace")

    def _validate_workflow(self, version) -> None:
        """Re-run the package checks (structure, manifest, L1 + L2) on the draft.

        The draft is zipped and validated with the same ``PackageValidator`` as
        an upload, so a new version can never be weaker than a first one. The
        manifest major must match the hub version (design §7.1): v2 needs
        ``version: 2.x.y``.
        """
        from app.features.workflow.package import PackageIssue, PackageValidator
        from app.features.workflow.services import WorkflowDatasetService

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, data in sorted(self._read_files(version).items()):
                archive.writestr(name, data)
        result = PackageValidator().validate_zip(buffer.getvalue())
        issues = list(result.issues)
        if result.valid:
            declared = str(result.manifest.get("version", ""))
            if declared.split(".", 1)[0] != str(version.number):
                issues.append(
                    PackageIssue(
                        f"La versión del manifiesto ({declared}) debe empezar por {version.number}, "
                        f"porque esta es la versión {version.number}.0 del workflow.",
                        file="actionhub.yaml",
                        field="version",
                    )
                )
        if issues:
            raise VersionError("La versión nueva no pasa la validación del workflow.", issues=issues)

        content = version.workflow_version
        content.manifest_json = json.dumps(result.manifest, ensure_ascii=False, sort_keys=True)
        content.workflow_yaml = result.workflow_yaml
        content.metadata_json = WorkflowDatasetService().metadata_json_for(result.workflow_yaml)
        # Only the draft's own rows change here. The dataset's grade still
        # describes the published version until the new one is published.
        db.session.flush()

    def _mirror_files(self, deposition_id: int, files) -> None:
        """Make the Zenodo draft hold exactly the version's files.

        ``newversion`` copies the previous files into the draft. They are all
        removed and the version's files uploaded again, which is also correct
        when retrying after a half-finished attempt.
        """
        from app.features.workflow.lifecycle import WorkflowPublicationService

        for existing in self.zenodo.get_deposition(deposition_id).get("files", []):
            self.zenodo.delete_file(deposition_id, existing["id"])
        for hubfile in files:
            self.zenodo.upload_file_from_path(
                deposition_id,
                self.hubfiles.get_path_by_hubfile(hubfile),
                WorkflowPublicationService.deposition_filename(hubfile.name),
            )
