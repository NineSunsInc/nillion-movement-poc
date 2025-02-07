from typing import Any, Callable, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models import BaseChatModel
from langgraph.store.memory import BaseStore

from agent_modules.agent.nodes.base import BaseNode
from agent_modules.database.types.state import PlanExecute

class LlmNode(BaseNode):
    """Node for handling llm-based tasks"""
    
    def __init__(self, 
                 prompt: str, 
                 llm: BaseChatModel, 
                 step: Callable,
                 output_schema: Optional[Any] = None) -> None:
        self.llm = llm
        self.prompt = prompt
        self.step = step
        self._initialize_node(output_schema)
        
    def _initialize_node(self, output_schema: Optional[Any]):
        full_prompt = ChatPromptTemplate([
            ("system", self.prompt),
            ("placeholder", "{messages}")
        ])
        
        # Create chain without callbacks to avoid tracing issues
        self.node = (full_prompt | self.llm.with_config({"callbacks": None}).with_structured_output(output_schema) 
                    if output_schema 
                    else full_prompt | self.llm.with_config({"callbacks": None}))

    def get_step(self):
        def agent_step(state: PlanExecute, store: BaseStore):
            return self.step(state, store, self.node)
        
        return agent_step