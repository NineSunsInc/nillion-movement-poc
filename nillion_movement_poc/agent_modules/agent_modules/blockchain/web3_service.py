from typing import Any, Dict, List
from web3 import Web3
from web3.middleware import SignAndSendRawMiddlewareBuilder, ExtraDataToPOAMiddleware
from web3.providers.rpc.utils import ExceptionRetryConfiguration

from agent_modules.blockchain.blockchain_base import BlockchainService
from agent_modules.blockchain.services.portals.portal_service import PolygonPortalService
from agent_modules.blockchain.services.swap.universal_router import UniversalRouter
from agent_modules.blockchain.services.swap.uniswap_router_v2 import RouterV2
from agent_modules.blockchain.services.oracles.uniswap_oracles import UniswapV3Oracles
from agent_modules.database.const.chain_config import Web3NetworkConfig
from agent_modules.database.const.common import ERC_20_TOKEN_ABI_PATH
from agent_modules.database.const.portals_yield_config import PortalsYieldConfigGetter
from agent_modules.blockchain.services.price.CoinGeckoService import CoinGeckoService

class SwapTokenPairValidator:
    @staticmethod
    def validate(network_config: Web3NetworkConfig, src_token: str, dest_token: str) -> None:
        valid_tokens = list(network_config.token_map.keys()) + [network_config.token_type]
        if src_token not in valid_tokens or dest_token not in valid_tokens:
            raise ValueError(f"Unsupported token pair. Only {", ".join(valid_tokens)} supported.")

class Web3Service(BlockchainService):
    def __init__(self, network_config: Web3NetworkConfig, private_key):
        self.network_config = network_config
        self.w3 = Web3(Web3.HTTPProvider(network_config.rpc_url, exception_retry_configuration=ExceptionRetryConfiguration(errors=[], retries=1, backoff_factor=0.125, method_allowlist=["eth_sendTransaction"]), request_kwargs={"timeout": 60}))

        # Different settings for each network env
        if (self.network_config.network_id == "POLYGON_AMOY"):
            self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        if (self.network_config.network_id == "ETH_SEPOLIA"):
            self.uniswap_service = UniversalRouter(w3=self.w3, network_config=network_config)
            self.oracles_service = UniswapV3Oracles(w3=self.w3, network_config=network_config)

        if (self.network_config.network_id == "ARBITRUM_SEPOLIA"):
            self.uniswap_service = RouterV2(w3=self.w3, network_config=network_config)

        if (self.network_config.network_id == "ARBITRUM_ONE"):
            self.uniswap_service = UniversalRouter(w3=self.w3, network_config=network_config)

        # TODO: For the demo 2024/12/11
        if (self.network_config.network_id == "POLYGON_POS"):
            self.portal_service = PolygonPortalService()

        self.private_key = private_key
        self.price_service = CoinGeckoService()
        self.gas = 1000000
        
    async def transfer_token(self, receiver_address: str, token_type: str, amount: float) -> Dict[str, Any]:
        account = self.w3.eth.account.from_key(self.private_key)
        self.w3.middleware_onion.add(SignAndSendRawMiddlewareBuilder.build(account))
        
        if (token_type != self.network_config.token_type):
            transfer_txn = self._create_erc20_transfer_tx(account, receiver_address, amount, token_type)
        else:
            transfer_txn = {
                "from": account.address,
                "value": self.w3.to_wei(amount, 'ether'),
                "to": receiver_address,
                "gas": self.gas,
                "nonce": self.w3.eth.get_transaction_count(account.address),
                "gasPrice": self.w3.eth.gas_price
            }

        tx = await self._execute_transaction(account, transfer_txn)
        
        return {
            "status": "success",
            "transaction_hash": tx["hash"],
            "from_address": account.address,
            "to_address": receiver_address,
            "amount": amount,
            "currency": token_type
        }
    
    async def get_balance(self, wallet_address: str, token_type: str = None, gas_unit_format: bool=False) -> float:
        if (token_type is None or token_type == self.network_config.token_type):
            balance = self.w3.eth.get_balance(wallet_address)
            return float(self.w3.from_wei(balance, "ether")) if (not gas_unit_format) else balance
        else:
            return self._get_erc20_token_balance(self.network_config.token_map[token_type], wallet_address, gas_unit_format)

    async def retrieve_available_tokens(self, wallet_address: str) -> Dict[str, float]:
        balance = await self.get_balance(wallet_address, self.network_config.token_type)

        token_balances = {}
        for token in self.network_config.token_map.keys():
            token_balances[token] = self._get_erc20_token_balance(self.network_config.token_map[token], wallet_address)

        return {
            **token_balances,
            self.network_config.token_type: balance
        }
    
    async def estimate_transfer_gas(self, receiver_address: str, token_type: str, amount: float) -> Dict[str, Any]:
        account = self.w3.eth.account.from_key(self.private_key)

        if (token_type != self.network_config.token_type):
            transfer_txn = self._create_erc20_transfer_tx(account, receiver_address, amount, token_type)
        else: 
            transfer_txn = {
                "from": account.address, # Any valid public key
                "value": self.w3.to_wei(amount, 'ether'),
                "to": receiver_address # Any valid public key
            }

        estimated_gas = self.w3.eth.estimate_gas(transfer_txn)

        return {
            "estimated_total_gas_cost": float(self.w3.from_wei(estimated_gas, 'ether')),
            "currency": self.network_config.token_type
        }

    async def estimate_swap_gas(self, amount: float, src_token: str, dest_token: str) -> Dict[str, Any]:
        account = self.w3.eth.account.from_key(self.private_key)
        
        # Validate token pair
        SwapTokenPairValidator.validate(self.network_config, src_token, dest_token)

        # Execute swap
        try:
            if (src_token != self.network_config.token_type):
                await self._approve_permit2(account, src_token)
                await self._approve_router(account, src_token)

            swap_txn = self._create_swap_tx(account, amount, src_token, dest_token)
            gas = self.w3.eth.estimate_gas(swap_txn)
            
            return {
                "estimated_total_gas_cost": float(self.w3.from_wei(gas, 'ether')),
                "currency": self.network_config.token_type
            }
        except Exception as e:
            print(e)
            raise Exception(f"Swap failed: {str(e)}")

    async def swap_tokens(self, amount: float, src_token: str, dest_token: str) -> Dict[str, Any]:
        if not self.uniswap_service:
            raise("Swap tokens unsupported")
        account = self.w3.eth.account.from_key(self.private_key)
        
        # Validate token pair
        SwapTokenPairValidator.validate(self.network_config, src_token, dest_token)

        # Execute swap
        try:
            if (src_token != self.network_config.token_type):
                await self._approve_permit2(account, src_token)
                await self._approve_router(account, src_token)

            swap_txn = self._create_swap_tx(account, amount, src_token, dest_token)
            return await self._execute_transaction(account, swap_txn)
        except Exception as e:
            raise Exception(f"Swap failed: {str(e)}")

    async def calculate_price_of_pair(self,  src_token: str, dest_token: str) -> float:
        if (self.network_config.network_id != "ETH_SEPOLIA"):
            raise Exception("Only Ethereum Sepolia Testnet supports calculate price of token pair")

        return self.oracles_service.calculate_pair_price(src_token, dest_token)

    def check_single_token_price(self, token_type: str) -> Dict[str, Any]:
        return self.price_service.check_single_token_price(token_type)
    
    def find_yields_for_wallet(self, wallet_address: str, yield_type: str) -> dict:
        if (not self.portal_service):
            raise Exception("Only Polygon mainnet supports finding yields for an account")

        yield_config = PortalsYieldConfigGetter.get_yield_config(yield_type)
        
        return self.portal_service.find_yields(wallet_address, yield_config)
    
    async def _approve_permit2(self, account, src_token: str):
        permit2_txn = self.uniswap_service.build_approve_permit2(account.address, src_token)
        await self._execute_transaction(account, permit2_txn)

    async def _approve_router(self, account, src_token: str):
        router_txn = self.uniswap_service.build_approve_router(account.address, src_token)
        await self._execute_transaction(account, router_txn)

    async def _execute_transaction(self, account, transaction: Dict) -> Dict[str, Any]:
        signed_txn = self.w3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        
        return {
            "success": True,
            "hash": tx_hash.hex(),
            "from_address": account.address
        }
    
    def _get_erc20_token_balance(self, token_address: str, wallet_address: str, gas_unit_format: bool=False) -> float:
        balance_abi = [
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [
                    {
                        "name": "",
                        "type": "uint8"
                    }
                ],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [
                    {
                        "name": "",
                        "type": "address"
                    }
                ],
                "name": "balanceOf",
                "outputs": [
                    {
                        "name": "",
                        "type": "uint256"
                    }
                ],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            }
        ]
        token_contract = self.w3.eth.contract(address=token_address, abi=balance_abi)
        balance = token_contract.functions.balanceOf(wallet_address).call()
        decimals = token_contract.functions.decimals().call()
        return balance / (10 ** decimals) if (not gas_unit_format) else balance

    def _create_swap_tx(self, account, amount: float, src_token: str, dest_token: str):
        swap_txn = self.uniswap_service.build_transaction(account.address, amount, src_token, dest_token)

        return swap_txn

    def _create_erc20_transfer_tx(self, account, to: str, amount: float, token_symbol: str):
        with open(ERC_20_TOKEN_ABI_PATH, "r") as f:
            erc20_abi = f.read()
        
        token_address = self.network_config.token_map[token_symbol]
        token_contract = self.w3.eth.contract(address=token_address, abi=erc20_abi)
        token_decimals = token_contract.functions.decimals().call()
        amount_in_wei = int(amount * (10 ** token_decimals))

        transfer_txn = token_contract.functions.transfer(to, amount_in_wei).build_transaction({
            "from": account.address,
            "value": 0,
            "gas": self.gas,
            "nonce": self.w3.eth.get_transaction_count(account.address)
        })

        return transfer_txn