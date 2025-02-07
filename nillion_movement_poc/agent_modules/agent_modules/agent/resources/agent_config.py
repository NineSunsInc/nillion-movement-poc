from dataclasses import dataclass

DEBUG = True

@dataclass
class AgentConfig:
    top_k: int = 5
    context_window: int = 5
