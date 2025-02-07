from typing import Any, Callable
from langgraph.store.base import BaseStore
from agent_modules.agent.nodes.base import BaseNode
from agent_modules.database.types.state import PlanExecute
from agent_modules.database.repositories.embedding_repository import EmbeddingRepository


class UserDataRetrieverNode(BaseNode):
    def __init__(self, user_data_embedding_repository: EmbeddingRepository, step):
        self.user_data_embedding_repository = user_data_embedding_repository
        self.step = step

    def get_step(self) -> Callable[..., Any]:
        def agent_step(state: PlanExecute, store: BaseStore):
            return self.step(state, store, self.user_data_embedding_repository)
        return agent_step