from typing import Dict
from web3 import Web3
from web3.contract.contract import Contract
from eth_abi import encode
from eth_abi.packed import encode_packed

from agent_modules.blockchain.services.swap.uniswap_base import SwapService
from agent_modules.database.const.chain_config import Web3NetworkConfig, ContractName
from agent_modules.database.const.common import ERC_20_TOKEN_ABI_PATH


class UniversalRouter(SwapService):
    def __init__(self, w3: Web3, network_config: Web3NetworkConfig):
        self.w3 = w3
        self.network_config = network_config

        # Commands for the Universal Router
        self.wrap_swap_commands = '0x0b00' # Wrap ETH command, SwapExact
        self.swap_command = '0x00' # SwapExact
        self.swap_unwrap_commands = '0x000c' # SwapExact, Unwrap WETH

        # Configuration for the Universal Router
        self.amount_out_min = 0
        self.from_eoa = False
        self.pool_fee = 500
        self.deadline = 2*10**10
        self.gas = 15**6
        self.permit2_max_allowance = 2**100 - 1  # max

        # Initialize the contracts and abis
        self.router_contract = self._initialize_router_contract()
        self.permit2_contract = self._initialize_permit2_contract()
        self.erc20_abi = self._initialize_erc20_abi()
        
    def build_path(self, token_in: str, token_out: str) -> list | bytes:
        token_in_address, token_out_address = self._get_token_pair_address(token_in, token_out)
        path = encode_packed(
            ['address', 'uint24', 'address'],
            [token_in_address, self.pool_fee, token_out_address]
        )

        return path

    def build_transaction(self, wallet_address, amount_in: int, token_in: str, token_out: str) -> Dict:
        amount_in_wei = self._calculate_amount_in_wei(amount_in, token_in)

        if (token_in == self.network_config.token_type):
            return self._build_native_token_source_transaction(wallet_address, amount_in_wei, token_out)
        
        elif (token_out == self.network_config.token_type):
            # This will only work if the token_in approved the permit2 contract to spend the tokens
            return self._build_native_token_destination_transaction(wallet_address, amount_in_wei, token_in)

        else:
            # This will only work if the token_in approved the permit2 contract to spend the tokens
            return self._build_non_native_token_transaction(wallet_address, amount_in_wei, token_in, token_out)
    
    # Specific for Universal Router + Permit2
    def build_approve_permit2(self, wallet_address: str, token_in: str):
        source_token_address = self.network_config.token_map[token_in]
        token_contract = self._initialize_token_contract(source_token_address)

        return token_contract.functions.approve(
            self.network_config.contract_map[ContractName.UNISWAP_PERMIT2].contract_address,
            self.permit2_max_allowance
        ).build_transaction({
            'from': wallet_address,
            'value': 0,
            'nonce': self.w3.eth.get_transaction_count(wallet_address),
            'gas': self.gas
        })

    # Specific for Universal Router + Permit2
    def build_approve_router(self, wallet_address: str, token_in: str):
        source_token_address = self.network_config.token_map[token_in]

        return self.permit2_contract.functions.approve(
            source_token_address,
            self.network_config.contract_map[ContractName.UNIVERSAL_ROUTER].contract_address,
            self.permit2_max_allowance,
            self.deadline
        ).build_transaction({
            'from': wallet_address,
            'value': 0,
            'nonce': self.w3.eth.get_transaction_count(wallet_address),
            'gas': self.gas
        })

    def _calculate_amount_in_wei(self, amount_in: int, token_in: str) -> int:
        if (token_in == self.network_config.token_type):
            amount_in_wei = self.w3.to_wei(amount_in, 'ether')
        else:
            token_in_address = self.network_config.token_map[token_in]
            token_in_contract = self._initialize_token_contract(token_in_address)
            decimals = token_in_contract.functions.decimals().call()
            amount_in_wei = int(amount_in * 10**decimals)
        
        return amount_in_wei

    def _build_native_token_source_transaction(self, wallet_address: str, amount_in_wei: int, token_out: str) -> Dict:
        # This is only workable for the Native token: Wrap ETH -> WETH -> create a token path from WETH to the destination token
        wrap_calldata = encode(
            ['address', 'uint256'],
            [self.router_contract.address, amount_in_wei]
        )

        # This is the token path from WETH to the destination token
        token_path = self.build_path(self.network_config.wrap_token_type, token_out)
        v3_calldata = encode(
            ['address', 'uint256', 'uint256', 'bytes', 'bool'],
            [wallet_address, amount_in_wei, self.amount_out_min, token_path, self.from_eoa]
        )

        return self.router_contract.functions.execute(
            self.wrap_swap_commands, 
            [wrap_calldata, v3_calldata], 
            self.deadline
        ).build_transaction({
            'from': wallet_address,
            'value': amount_in_wei,
            'nonce': self.w3.eth.get_transaction_count(wallet_address),
            'gas': self.gas
        })

    def _build_native_token_destination_transaction(self, wallet_address: str, amount_in_wei: int, token_in: str) -> Dict:
        token_path = self.build_path(token_in, self.network_config.wrap_token_type)
        v3_calldata = encode(
            ['address', 'uint256', 'uint256', 'bytes', 'bool'],
            [self.router_contract.address, amount_in_wei, self.amount_out_min, token_path, True]
        )

        unwrap_calldata = encode(
            ['address', 'uint256'],
            [wallet_address, self.amount_out_min]
        )

        return self.router_contract.functions.execute(
            self.swap_unwrap_commands, 
            [v3_calldata, unwrap_calldata], 
            self.deadline
        ).build_transaction({
            'from': wallet_address,
            'value': 0,
            'nonce': self.w3.eth.get_transaction_count(wallet_address),
            'gas': self.gas
        })

    def _build_non_native_token_transaction(self, wallet_address: str, amount_in_wei: int, token_in: str, token_out: str) -> Dict:
        token_path = self.build_path(token_in, token_out)
        v3_calldata = encode(
            ['address', 'uint256', 'uint256', 'bytes', 'bool'],
            [wallet_address, amount_in_wei, self.amount_out_min, token_path, True]
        )

        return self.router_contract.functions.execute(
            self.swap_command, 
            [v3_calldata], 
            self.deadline
        ).build_transaction({
            'from': wallet_address,
            'value': 0,
            'nonce': self.w3.eth.get_transaction_count(wallet_address),
            'gas': self.gas
        })

    def _initialize_erc20_abi(self) -> list:
        with open(ERC_20_TOKEN_ABI_PATH, "r") as abi_file:
            return abi_file.read() 

    def _initialize_token_contract(self, token_adress) -> Contract:
        return self.w3.eth.contract(address=token_adress, abi=self.erc20_abi)

    def _initialize_permit2_contract(self) -> Contract:
        contract_config = self.network_config.contract_map[ContractName.UNISWAP_PERMIT2]

        with open(contract_config.contract_abi_path, "r") as abi_file:
            permit2_abi = abi_file.read()

        return self.w3.eth.contract(address=contract_config.contract_address, abi=permit2_abi)

    def _initialize_router_contract(self) -> Contract:
        contract_config = self.network_config.contract_map[ContractName.UNIVERSAL_ROUTER]

        contract_address = contract_config.contract_address
        abi_path = contract_config.contract_abi_path

        with open(abi_path, "r") as abi_file:
            abi = abi_file.read()
    
        return self.w3.eth.contract(address=contract_address, abi=abi)

    def _get_token_pair_address(self, src_token: str, dest_token: str):
        """Get the token address on a specific chain"""
        token_dict = self.network_config.token_map
        return token_dict[src_token], token_dict[dest_token]