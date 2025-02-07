
from dataclasses import dataclass

@dataclass
class ContractConfig:
    """The router contract config"""
    contract_address: str
    contract_abi_path: str