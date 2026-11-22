import re
from datetime import date, datetime, time, timedelta

import unidecode
from splent_framework.repositories.BaseRepository import BaseRepository
from sqlalchemy import or_

from app.features.dataset.models import Author, DataSet, DSMetaData, PublicationType
from app.features.featuremodel.models import FeatureModel, FMMetaData


class ExploreRepository(BaseRepository):
    def __init__(self):
        super().__init__(DataSet)

    def filter(
        self,
        query="",
        sorting="newest",
        publication_type="any",
        tags=[],
        author="",
        start_date="",
        end_date="",
        **kwargs,
    ):
        # Normalize and remove unwanted characters
        normalized_query = unidecode.unidecode(query).lower()
        cleaned_query = re.sub(r'[,.":\'()\[\]^;!¡¿?]', "", normalized_query)

        filters = []
        for word in cleaned_query.split():
            filters.append(DSMetaData.title.ilike(f"%{word}%"))
            filters.append(DSMetaData.description.ilike(f"%{word}%"))
            filters.append(Author.name.ilike(f"%{word}%"))
            filters.append(Author.affiliation.ilike(f"%{word}%"))
            filters.append(Author.orcid.ilike(f"%{word}%"))
            filters.append(FMMetaData.uvl_filename.ilike(f"%{word}%"))
            filters.append(FMMetaData.title.ilike(f"%{word}%"))
            filters.append(FMMetaData.description.ilike(f"%{word}%"))
            filters.append(FMMetaData.publication_doi.ilike(f"%{word}%"))
            filters.append(FMMetaData.tags.ilike(f"%{word}%"))
            filters.append(DSMetaData.tags.ilike(f"%{word}%"))

        datasets = (
            self.model.query.join(DataSet.ds_meta_data)
            .join(DSMetaData.authors)
            .join(DataSet.feature_models)
            .join(FeatureModel.fm_meta_data)
            .filter(or_(*filters))
            .filter(DSMetaData.dataset_doi.isnot(None))  # Exclude datasets with empty dataset_doi
        )

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
            datasets = datasets.filter(self.model.created_at >= datetime.combine(start_day, time.min))

        end_day = self._parse_date(end_date)
        if end_day is not None:
            next_day = datetime.combine(end_day + timedelta(days=1), time.min)
            datasets = datasets.filter(self.model.created_at < next_day)

        # Order by created_at
        if sorting == "oldest":
            datasets = datasets.order_by(self.model.created_at.asc())
        else:
            datasets = datasets.order_by(self.model.created_at.desc())

        return datasets.all()

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
