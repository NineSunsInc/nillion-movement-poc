from abc import ABC, abstractmethod
from typing import Any, Callable
from langchain_core.callbacks import CallbackManager
from langchain_core.tracers import ConsoleCallbackHandler

class BaseNode(ABC):
    """Abstract base class for all nodes"""
    
    @abstractmethod
    def get_step(self) -> Callable[..., Any]:
        """Returns the step function for this node"""
        pass
    
    def _create_callback_manager(self):
        """Create a simple callback manager that won't cause tracing issues"""
        return CallbackManager([ConsoleCallbackHandler()])