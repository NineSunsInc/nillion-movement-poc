from typing import Any, Callable
from langchain_core.language_models import BaseChatModel
from langgraph.store.memory import BaseStore

from agent_modules.agent.nodes.base import BaseNode
from agent_modules.database.types.state import PlanExecute


class DynamicFormatterNode(BaseNode):
    def __init__(self, llm: BaseChatModel, step: Callable):
        self.llm = llm.with_config({"callbacks": None})  # Disable callbacks
        self.step = step

    def get_step(self) -> Callable[..., Any]:
        def formatter_step(state: PlanExecute, store: BaseStore):
            return self.step(state, store, self.llm)
        
        return formatter_step