import os
import httpx

from dotenv import load_dotenv
from typing import Any, Dict, List

from aptos_sdk.account import Account
from aptos_sdk.account_address import AccountAddress
from aptos_sdk.async_client import RestClient
from aptos_sdk.type_tag import StructTag, TypeTag
from aptos_sdk.bcs import Serializer
from aptos_sdk.transactions import (
    EntryFunction,
    TransactionArgument,
    TransactionPayload,
)
from aptos_sdk.metadata import Metadata


from agent_modules.blockchain.blockchain_base import BlockchainService

from agent_modules.database.const.common import token_contracts_move_ecosystem, unit_to_factor
from agent_modules.database.types.portals_type import PortalsTokenData
from agent_modules.database.const.chain_config import NetworkConfig
from agent_modules.blockchain.services.price.CoinGeckoService import CoinGeckoService

class AptosService(BlockchainService):
    def __init__(self, network_config: NetworkConfig, private_key: str):
        self.rest_client = RestClient(network_config.rpc_url)

        # Replace the default async client with a custom one
        self.rest_client.client = self._create_custom_async_client()

        self.network_config = network_config
        self.private_key = private_key
        self.price_service = CoinGeckoService()

    def _create_custom_async_client(self):

        # Default limits
        limits = httpx.Limits()
        # Default timeouts but do not set a pool timeout, since the idea is that jobs will wait as
        # long as progress is being made.
        timeout = httpx.Timeout(60.0, pool=None)
        # Default headers
        headers = {Metadata.APTOS_HEADER: Metadata.get_aptos_header_val(), 'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.76 Safari/537.36'}

        return httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            headers=headers
        )

    async def transfer_token(self, receiver_address: str, token_type: str, amount: float) -> Dict[str, Any]:
        wallet = Account.load_key(self.private_key)
        txn_hash = await self.rest_client.bcs_transfer(
            wallet, 
            AccountAddress.from_str_relaxed(receiver_address), 
            int(amount * (10 ** 8))
        )
        
        await self.rest_client.wait_for_transaction(txn_hash)
        
        return {
            "status": "success",
            "transaction_hash": txn_hash,
            "from_address": wallet.account_address.address.hex(),
            "to_address": receiver_address,
            "amount": amount,
            "currency": "MOVE"
        }
    
    async def get_balance(self, wallet_address: str, token_type: str, gas_unit_format: bool=False) -> float:
        mtype = token_contracts_move_ecosystem[token_type]
        factor = unit_to_factor[token_type]

        balance = await self.rest_client.view_bcs_payload(
            "0x1::coin",
            "balance",
            [TypeTag(StructTag.from_str(mtype))],
            [TransactionArgument(AccountAddress.from_str_relaxed(wallet_address), Serializer.struct)],
        )

        return float(balance[0]) / factor if (not gas_unit_format) else float(balance[0])
    
    async def retrieve_available_tokens(self, wallet_address: str) -> Dict[str, float]:
        resources = await self.rest_client.account_resources(
            account_address = AccountAddress.from_str_relaxed(wallet_address)
        )
        tokens = {}
        for resource in resources:
            if ("0x1::coin::CoinStore" in resource["type"]):
                mtype = resource["type"][21:-1]
                type = list(token_contracts_move_ecosystem.keys())[list(token_contracts_move_ecosystem.values()).index(mtype)]
                factor = unit_to_factor[type]
                tokens[type] = float(resource["data"]["coin"]["value"]) / factor

        return tokens

    async def estimate_transfer_gas(self, receiver_address: str, token_type: str, amount: float) -> Dict[str, Any]:
        # This is just a test account for estimating the gas (APTOS needs a real account for this process)
        wallet = Account.load_key(os.getenv("GAS_ESTIMATING_PRIVATE_KEY"))

        # Payload of the transaction
        # Currently only support for native token
        payload = EntryFunction.natural(
            "0x1::coin",
            "transfer",
            [TypeTag(StructTag.from_str(token_contracts_move_ecosystem['MOVE']))],
            [
                TransactionArgument(AccountAddress.from_str_relaxed(os.getenv("ESTIMATING_APTOS_PUBLIC_KEY_1")), Serializer.struct), # Any valid wallet address
                TransactionArgument(int(amount * (unit_to_factor['MOVE'])), Serializer.u64),
            ],
        )

        transaction = await self.rest_client.create_bcs_transaction(
            wallet, TransactionPayload(payload)
        )

        simulation = await self.rest_client.simulate_transaction(
            transaction=transaction,
            sender=wallet,
            estimate_gas_usage=True
        )

        estimated_gas = int(simulation[0]['events'][-1]['data']['total_charge_gas_units']) * int(simulation[0]['gas_unit_price'])

        return {
            "estimated_total_gas_cost": estimated_gas / unit_to_factor[self.network_config.token_type],
            "currency": self.network_config.token_type
        }

    async def estimate_swap_gas(self, amount: float, src_token: str, dest_token: str) -> Dict[str, Any]:
        load_dotenv()
    
        msrc_type = token_contracts_move_ecosystem[src_token]
        factor_src_type = unit_to_factor[dest_token]
        mdes_type = token_contracts_move_ecosystem[dest_token]

        # This is just a test account for estimating the gas (APTOS needs a real account for this process)
        wallet = Account.load_key(os.getenv("GAS_ESTIMATING_PRIVATE_KEY"))

        payload = EntryFunction.natural(
            "0x65c7939df25c4986b38a6af99602bf17daa1a2d7b53e6847ed25c04f74f54607::RazorSwapPool",
            "swap_exact_coins_for_coins_entry",
            [
                TypeTag(StructTag.from_str(msrc_type)),
                TypeTag(StructTag.from_str(mdes_type)),
            ],
            [
                TransactionArgument(int(amount * (factor_src_type)), Serializer.u64),
                TransactionArgument(1, Serializer.u64)
            ],
        )

        signed_transaction = await self.rest_client.create_bcs_signed_transaction(
            wallet, TransactionPayload(payload)
        )

        simulation = await self.rest_client.simulate_bcs_transaction(signed_transaction, True)
        estimated_gas = int(simulation[0]['events'][-1]['data']['total_charge_gas_units']) * int(simulation[0]['gas_unit_price'])
        return {
            "estimated_total_gas_cost": estimated_gas / unit_to_factor[self.network_config.token_type],
            "currency": self.network_config.token_type
        }
    
    async def swap_tokens(self, amount: float, src_token: str, dest_token: str) -> Dict[str, Any]:
        # Get aptos wallet private key because we only support on APTOS environment

        msrc_type = token_contracts_move_ecosystem[src_token]
        factor_src_type = unit_to_factor[src_token]

        mdes_type = token_contracts_move_ecosystem[dest_token]

        wallet = Account.load_key(self.private_key)

        payload = EntryFunction.natural(
            "0x65c7939df25c4986b38a6af99602bf17daa1a2d7b53e6847ed25c04f74f54607::RazorSwapPool",
            "swap_exact_coins_for_coins_entry",
            [
                TypeTag(StructTag.from_str(msrc_type)),
                TypeTag(StructTag.from_str(mdes_type)),
            ],
            [
                TransactionArgument(int(amount * (factor_src_type)), Serializer.u64),
                TransactionArgument(1, Serializer.u64) # Should we use 1 for this?
            ],
        )

        signed_transaction = await self.rest_client.create_bcs_signed_transaction(
            wallet, TransactionPayload(payload)
        )

        result = await self.rest_client.submit_and_wait_for_bcs_transaction(signed_transaction)
        return result
    
    async def calculate_price_of_pair(self, src_token: str, dest_token: str) -> float:
        raise Exception("Unsupport tool")
    
    def find_yields_for_wallet(self, wallet_address, yield_type: str) -> List[PortalsTokenData]:
        raise Exception("Unsupport tool")
    
    def check_single_token_price(self, token_type: str) -> Dict[str, Any]:
        return self.price_service.check_single_token_price(token_type)