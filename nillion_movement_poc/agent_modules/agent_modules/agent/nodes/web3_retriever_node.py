from typing import Any, Callable
from langgraph.store.base import BaseStore
from sentence_transformers import CrossEncoder
from agent_modules.agent.nodes.base import BaseNode
from agent_modules.database.types.state import PlanExecute
from agent_modules.database.repositories.opensearch_repository import OpenSearchRepository


class Web3RetrieverNode(BaseNode):
    def __init__(self, opensearch_repository: OpenSearchRepository, cross_encoder: CrossEncoder, step):
        self.opensearch_repository = opensearch_repository
        self.cross_encoder = cross_encoder
        self.step = step

    def get_step(self) -> Callable[..., Any]:
        def agent_step(state: PlanExecute, store: BaseStore):
            return self.step(state, store, self.opensearch_repository, self.cross_encoder)
        return agent_step
