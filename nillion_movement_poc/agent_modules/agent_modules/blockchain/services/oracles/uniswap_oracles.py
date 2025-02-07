from dataclasses import dataclass
from typing import List

from web3 import Web3
from web3.contract.contract import Contract

from agent_modules.blockchain.services.oracles.oracle_base import OraclesService
from agent_modules.database.const.chain_config import ContractName, Web3NetworkConfig
from agent_modules.database.types.observation import Observation
from agent_modules.database.const.common import ERC_20_TOKEN_ABI_PATH, UNISWAP_POOL_ABI_PATH

class UniswapV3Oracles(OraclesService):
    def __init__(self, w3: Web3, network_config: Web3NetworkConfig) -> None:
        self.w3 = w3
        self.network_config = network_config
        self.contract = self._initialize_factory_contract()
        self.seconds_ago = 108
        self.fee = 3000
        self.tick_factor = 1.0001

    def calculate_pair_price(self, src_token: str, dest_token: str):
        # Get token's addresses from const file
        src_address, dest_address = self._get_token_pair_address(src_token, dest_token)
        
        # Get pool information
        pool = self._get_pool(src_address, dest_address, self.fee)
        token0_address = pool.functions.token0().call()
        token1_address = pool.functions.token1().call()
        token0_decimals = self._find_token_decimals(token0_address)
        token1_decimals = self._find_token_decimals(token1_address) 

        # Find the observations
        observations = self._observe(pool)
        avarage_tick = self._calculate_avarage_tick(observations)

        # Calculate price using avarage tick
        price = self.tick_factor ** avarage_tick
        price = price * 10**(token0_decimals - token1_decimals)

        reverse = token0_address != src_address
        return {
            "reverse": reverse,
            "price": price if not reverse else 1 / price
        } 

    def _calculate_avarage_tick(self, observations: List[Observation]) -> int:
        diff_tick_cumulative = observations[0].tick_cumulative - observations[1].tick_cumulative
        seconds_between = observations[1].seconds_ago - observations[0].seconds_ago
        avarage_tick = diff_tick_cumulative / seconds_between
        return int(avarage_tick)

    def _get_pool(self, src_token_addr: str, dest_token_addr: str, fee: int) -> Contract:
        address = self.contract.functions.getPool(Web3.to_checksum_address(src_token_addr), Web3.to_checksum_address(dest_token_addr), fee).call()
        with open(UNISWAP_POOL_ABI_PATH, "r") as abi_file:
            abi = abi_file.read()
    
        pool = self.w3.eth.contract(address=address, abi=abi)
        return pool
        
    def _observe(self, pool: Contract):                
        timestamps = [0, self.seconds_ago]
        tick_cumulatives, seconds_per_liquidity_cumulatives = pool.functions.observe(timestamps).call()
        observations = [Observation(time, tick_cumulatives[i], seconds_per_liquidity_cumulatives[i]) for i, time in enumerate(timestamps)]

        return observations

    def _find_token_decimals(self, token_address: str):
        token_contract = self._get_token_contract(token_address)
        return token_contract.functions.decimals().call()

    def _initialize_factory_contract(self) -> Contract:
        contract_config = self.network_config.contract_map[ContractName.UNISWAP_FACTORY_V3]

        contract_address = contract_config.contract_address
        abi_path = contract_config.contract_abi_path

        with open(abi_path, "r") as abi_file:
            abi = abi_file.read()
    
        return self.w3.eth.contract(address=contract_address, abi=abi)
    
    def _get_token_contract(self, token_address: str):
        with open(ERC_20_TOKEN_ABI_PATH, "r") as abi_file:
            abi = abi_file.read()

        return self.w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=abi)
    
    def _get_token_pair_address(self, src_token: str, dest_token: str):
        """Get the token address on a specific chain"""
        token_dict = self.network_config.token_map
        return token_dict[src_token], token_dict[dest_token]