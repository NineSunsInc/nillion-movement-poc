from typing import List
from dataclasses import dataclass

@dataclass
class SafetyResult:
    status: str
    safety_score: float
    triggered_keywords: List[str]