import re
from datetime import date, datetime, time, timedelta

import unidecode
from splent_framework.repositories.BaseRepository import BaseRepository
from sqlalchemy import or_

from app.features.dataset.models import Author, BaseDataset, DSMetaData, PublicationType
from app.features.featuremodel.models import FeatureModel, FMMetaData
from app.features.workflow.models import WorkflowVersion

DATASET_TYPES = ("uvl", "workflow")


class ExploreRepository(BaseRepository):
    """Type-aware dataset search (#20).

    The catalogue is queried through ``BaseDataset``, not the UVL subclass. All
    type-specific joins are outer joins, so a published workflow dataset (or a
    UVL dataset without a feature model) is still returned. The optional
    ``dataset_type`` filter narrows the result to one concrete type.
    """

    def __init__(self):
        super().__init__(BaseDataset)

    def filter(
        self,
        query="",
        sorting="newest",
        publication_type="any",
        tags=[],
        author="",
        start_date="",
        end_date="",
        dataset_type="any",
        **kwargs,
    ):
        # Normalize and remove unwanted characters
        normalized_query = unidecode.unidecode(query).lower()
        cleaned_query = re.sub(r'[,.":\'()\[\]^;!¡¿?]', "", normalized_query)

        filters = []
        for word in cleaned_query.split():
            # Common metadata: matches every dataset type.
            filters.append(DSMetaData.title.ilike(f"%{word}%"))
            filters.append(DSMetaData.description.ilike(f"%{word}%"))
            filters.append(Author.name.ilike(f"%{word}%"))
            filters.append(Author.affiliation.ilike(f"%{word}%"))
            filters.append(Author.orcid.ilike(f"%{word}%"))
            filters.append(DSMetaData.tags.ilike(f"%{word}%"))
            # UVL-specific content.
            filters.append(FMMetaData.uvl_filename.ilike(f"%{word}%"))
            filters.append(FMMetaData.title.ilike(f"%{word}%"))
            filters.append(FMMetaData.description.ilike(f"%{word}%"))
            filters.append(FMMetaData.publication_doi.ilike(f"%{word}%"))
            filters.append(FMMetaData.tags.ilike(f"%{word}%"))
            # Workflow-specific content.
            filters.append(WorkflowVersion.workflow_yaml.ilike(f"%{word}%"))
            filters.append(WorkflowVersion.manifest_json.ilike(f"%{word}%"))

        datasets = (
            self.model.query.join(DSMetaData, BaseDataset.ds_meta_data_id == DSMetaData.id)
            .outerjoin(Author, Author.ds_meta_data_id == DSMetaData.id)
            .outerjoin(FeatureModel, FeatureModel.data_set_id == BaseDataset.id)
            .outerjoin(FMMetaData, FeatureModel.fm_meta_data_id == FMMetaData.id)
            .outerjoin(WorkflowVersion, WorkflowVersion.workflow_dataset_id == BaseDataset.id)
            # A dataset is publicly discoverable only after its first DOI.
            .filter(DSMetaData.dataset_doi.isnot(None))
        )

        if filters:
            datasets = datasets.filter(or_(*filters))

        dataset_type = str(dataset_type or "any").lower()
        if dataset_type in DATASET_TYPES:
            datasets = datasets.filter(BaseDataset.type == dataset_type)

        if publication_type != "any":
            matching_type = None
            for member in PublicationType:
                if member.value.lower() == publication_type:
                    matching_type = member
                    break

            if matching_type is not None:
                datasets = datasets.filter(DSMetaData.publication_type == matching_type.name)

        if tags:
            datasets = datasets.filter(or_(*(DSMetaData.tags.ilike(f"%{tag}%") for tag in tags)))

        author = str(author or "").strip()
        if author:
            author_term = unidecode.unidecode(author).lower()
            datasets = datasets.filter(
                or_(
                    Author.name.ilike(f"%{author_term}%"),
                    Author.affiliation.ilike(f"%{author_term}%"),
                    Author.orcid.ilike(f"%{author_term}%"),
                )
            )

        start_day = self._parse_date(start_date)
        if start_day is not None:
            datasets = datasets.filter(BaseDataset.created_at >= datetime.combine(start_day, time.min))

        end_day = self._parse_date(end_date)
        if end_day is not None:
            next_day = datetime.combine(end_day + timedelta(days=1), time.min)
            datasets = datasets.filter(BaseDataset.created_at < next_day)

        if sorting == "oldest":
            datasets = datasets.order_by(BaseDataset.created_at.asc())
        else:
            datasets = datasets.order_by(BaseDataset.created_at.desc())

        # A dataset may have several authors, feature models or workflow
        # versions; the outer joins produce one row per combination.
        return datasets.distinct().all()

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
