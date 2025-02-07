from typing import Any, Callable
from agent_modules.agent.nodes.base import BaseNode


class FunctionNode(BaseNode):
    def __init__(self, step: Callable):
        self.step = step

    def get_step(self) -> Callable[..., Any]:
        return self.step