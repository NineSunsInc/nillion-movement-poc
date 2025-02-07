from abc import ABC
from typing import Dict

class SwapService(ABC):
    """Baes class for swap service"""
    def build_transaction(self, wallet_address, amount_in: int, token_in: str, token_out: str) -> Dict:
        pass