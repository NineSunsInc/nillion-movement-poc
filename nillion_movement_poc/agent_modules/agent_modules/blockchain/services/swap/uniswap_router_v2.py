from web3 import Web3
from web3.contract.contract import Contract
from typing import Dict

from agent_modules.blockchain.services.swap.uniswap_base import SwapService
from agent_modules.database.const.chain_config import ContractName, Web3NetworkConfig

class RouterV2(SwapService):
    def __init__(self, w3: Web3, network_config: Web3NetworkConfig):
        self.w3 = w3
        self.network_config = network_config
        self.router_contract = self._initialize_router_contract()
        self.gas = 10**6
        self.deadline = 2*10**10
        self.amount_out_min = 0
    
    def build_path(self, token_in: str, token_out: str) -> list | bytes:
        src_token_address, dest_token_address = self._get_token_pair_address(token_in, token_out)

        return [Web3.to_checksum_address(src_token_address), dest_token_address]
    
    def build_transaction(self, wallet_address, amount_in: int, token_in: str, token_out: str) -> Dict:
        amount_in_wei = self.w3.to_wei(amount_in, 'ether')

        path = self.build_path(token_in, token_out)

        return self.router_contract.functions.swapExactETHForTokens(
            self.amount_out_min, # amount_out_min
            path,
            wallet_address,
            self.deadline
        ).build_transaction({
            'from': wallet_address,
            'value': amount_in_wei,
            'nonce': self.w3.eth.get_transaction_count(wallet_address),
            'gas': self.gas
        })

    def _get_deadline(self) -> int:
        return self.w3.eth.get_block('latest').timestamp + 60 * 20

    def _get_token_pair_address(self, src_token: str, dest_token: str):
        """Get the token address on a specific chain"""
        token_dict = self.network_config.token_map
        return token_dict[src_token], token_dict[dest_token]
    
    def _initialize_router_contract(self) -> Contract:
        contract_config = self.network_config.contract_map[ContractName.UNISWAP_ROUTER_V2]

        contract_address = contract_config.contract_address
        abi_path = contract_config.contract_abi_path

        with open(abi_path, "r") as abi_file:
            abi = abi_file.read()
    
        return self.w3.eth.contract(address=contract_address, abi=abi)