from typing import Annotated
from agent_modules.database.repositories.embedding_repository import EmbeddingRepository
from agent_modules.database.repositories.opensearch_repository import OpenSearchRepository
from agent_modules.embedding.embedding_service import MiniLmEmbeddingService
from agent_modules.opensearch.opensearch_service import OpenSearchService
from dishka import FromComponent, Provider, Scope, provide


class DatabaseFactory(Provider):
    @provide(scope=Scope.APP)
    def provide_opensearch_repository(
        self,
        opensearch_service: Annotated[OpenSearchService, FromComponent()],
    ) -> OpenSearchRepository:
        return OpenSearchRepository(index_name="cleaned_blockchain_docs", opensearch_service=opensearch_service)

    @provide(scope=Scope.APP)
    def provide_user_data_embedding_repository(
        self,
        embedding_service: Annotated[MiniLmEmbeddingService, FromComponent()],
    ) -> EmbeddingRepository:
        return EmbeddingRepository("user_data", embedding_service)
