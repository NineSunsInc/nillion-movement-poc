from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum

from agent_modules.database.const.contract_name import ContractName
from agent_modules.database.types.contract_config import ContractConfig

class ExplorerUrlType(Enum):
    TRANSACTION = "transaction"
    ADDRESS = "address"
    TOKEN = "token"

@dataclass
class ExplorerConfig:
    base_url: str
    transaction_path: str = "tx"  # Default for EVM
    address_path: str = "address"
    token_path: str = "token"
    network_param: Optional[str] = None  # e.g., "?network=testnet"
    
    def get_transaction_url(self, tx_hash: str) -> str:
        url = f"{self.base_url.rstrip('/')}/{self.transaction_path}/{tx_hash}"
        if self.network_param:
            url += self.network_param
        return url
    
    def get_address_url(self, address: str) -> str:
        url = f"{self.base_url.rstrip('/')}/{self.address_path}/{address}"
        if self.network_param:
            url += self.network_param
        return url
    
    def get_token_url(self, token_address: str) -> str:
        url = f"{self.base_url.rstrip('/')}/{self.token_path}/{token_address}"
        if self.network_param:
            url += self.network_param
        return url

@dataclass
class NetworkConfig:
    name: str
    network_id: str
    token_type: str
    rpc_url: str
    config_keys: tuple[str, str]
    explorer: ExplorerConfig

@dataclass
class Web3NetworkConfig:
    name: str
    network_id: str
    token_type: str
    wrap_token_type: str
    rpc_url: str
    config_keys: tuple[str, str]
    contract_map: Dict[str, any]  # Using 'any' for ContractConfig
    token_map: Dict[str, str]
    explorer: ExplorerConfig