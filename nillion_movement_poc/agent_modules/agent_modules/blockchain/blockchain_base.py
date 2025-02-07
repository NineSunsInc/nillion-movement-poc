from abc import ABC, abstractmethod
from typing import Dict, Any, List

from agent_modules.database.types.portals_type import PortalsTokenData

class BlockchainService(ABC):
    """Base class for blockchain interactions"""
    
    @abstractmethod
    async def transfer_token(self, receiver_address: str, token_type: str, amount: float) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def get_balance(self, wallet_address: str, token_type: str, gas_unit_format: bool=False) -> float:
        pass
    
    @abstractmethod
    async def estimate_transfer_gas(self, wallet_address: str, token_type: str, amount: float) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def estimate_swap_gas(self, amount: float, src_token: str, dest_token: str) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def swap_tokens(self, amount: float, src_token: str, dest_token: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def retrieve_available_tokens(self, wallet_address: str) -> Dict[str, float]:
        pass

    @abstractmethod
    async def calculate_price_of_pair(self, src_token: str, dest_token: str) -> float:
        pass

    @abstractmethod
    def find_yields_for_wallet(self, wallet_address, yield_type: str) -> List[PortalsTokenData]:
        pass

    @abstractmethod
    def check_single_token_price(self, token_type: str) -> Dict[str, Any]:
        pass
