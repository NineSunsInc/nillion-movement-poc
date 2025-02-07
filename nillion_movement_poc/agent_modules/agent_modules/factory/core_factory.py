from typing import Annotated
from agent_modules.embedding.embedding_service import MiniLmEmbeddingService
from agent_modules.opensearch.opensearch_service import OpenSearchService
from dishka import FromComponent, Provider, Scope, provide
from sentence_transformers import CrossEncoder


class CoreFactory(Provider):
    @provide(scope=Scope.APP)
    def provide_opensearch_service(
        self,
        embedding_service: Annotated[MiniLmEmbeddingService, FromComponent()],
    ) -> OpenSearchService:
        return OpenSearchService(embedding_service)

    @provide(scope=Scope.APP)
    def provide_cross_encoder(self) -> CrossEncoder:
        return CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
