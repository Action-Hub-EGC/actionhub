from splent_framework.services.BaseService import BaseService

from app.features.explore.repositories import ExploreRepository


class ExploreService(BaseService):
    def __init__(self):
        super().__init__(ExploreRepository())

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
        return self.repository.filter(
            query=query,
            sorting=sorting,
            publication_type=publication_type,
            tags=tags,
            author=author,
            start_date=start_date,
            end_date=end_date,
            **kwargs,
        )
