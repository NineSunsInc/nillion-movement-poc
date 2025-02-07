from dataclasses import dataclass

@dataclass
class LLMConfig:
    model: str = None
    temperature: float = 0