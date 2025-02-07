from typing import Dict

from agent_modules.blockchain.blockchain_base import BlockchainService
from agent_modules.blockchain.web3_service import Web3Service
from agent_modules.blockchain.aptos_service import AptosService

class BlockchainServiceFactory:
    """Factory for creating blockchain service instances"""
    
    @staticmethod
    def create_service(network_env: str, config: Dict, private_key) -> BlockchainService:
        if network_env in ["MEVM", "POLYGON_AMOY", "ETH_SEPOLIA", "POLYGON_POS", "ARBITRUM_SEPOLIA", "ARBITRUM_ONE"]:
            return Web3Service(config, private_key)
        elif network_env in ["APTOS", "PORTO"]:
            return AptosService(config, private_key)
        raise ValueError(f"Unsupported network: {network_env}")
