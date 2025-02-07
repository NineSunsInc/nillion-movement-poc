from agent_modules.embedding.embedding_service import MiniLmEmbeddingService
from dishka import Provider, Scope, provide

class EmbeddingFactory(Provider):
    @provide(scope=Scope.APP)
    def provide_embedding_service(self) -> MiniLmEmbeddingService:
        return MiniLmEmbeddingService().get_service()
