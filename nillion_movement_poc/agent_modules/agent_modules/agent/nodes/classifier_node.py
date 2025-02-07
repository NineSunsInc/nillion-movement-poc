import os
from typing import Any, Callable
from langgraph.store.base import BaseStore

from agent_modules.agent.nodes.base import BaseNode
from agent_modules.database.types.state import PlanExecute


class ClassifierNode(BaseNode):
    def __init__(self, step, classifier, *args: Any) -> None:
        self.classifier = classifier
        self.step = step
        self.args = args
        
    def get_step(self) -> Callable[..., Any]:
        def agent_step(state: PlanExecute, store: BaseStore):
            return self.step(state, store, self.classifier, *self.args)

        return agent_step
