
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class ResponseRecord:
    id: int
    input: str
    response: str
    past_steps: List[Tuple]
    category: str
    chain: str
    expiration: int