import os
import json
import dataclasses

from typing import List
from requests import get
from dotenv import load_dotenv

from agent_modules.database.types.portals_type import PortalsMetric, PortalsTokenData, PortalTokenInfo, PortalsYieldConfig

class PolygonPortalService:
    def __init__(self) -> None:
        load_dotenv()
        self.url = os.getenv("PORTALS_API_URL")
        self.api_key = os.getenv("PORTALS_API_KEY")
        self.top_k = 3

    def get_wallet_balance(self, account_address: str) -> List[PortalTokenInfo]:
        request_content = get(
            self.url + f"/v2/account",
            params={
                "owner": account_address,
                "networks": "polygon"
            },
            headers={"Authorization": "Bearer " + self.api_key}
        ).content


        wallet_balance = json.loads(request_content)["balances"]
        tokens = [
            PortalTokenInfo(token["symbol"], token["address"], token["balanceUSD"], token["balance"], token["rawBalance"]) 
            for token in wallet_balance
        ]

        return tokens
    
    def get_token_data(self, search_token_symbols: List[str], sorted_by: str = "apy", sort_direction: str = "desc", limit: int = 25, min_apy: float = 3.0, max_apy: float = 50.0, min_liquidity: float = 10000) -> List[PortalsTokenData]:
        requested_content = get(
            self.url + "/v2/tokens",
            params={
                "search": " ".join(search_token_symbols),
                "networks": "polygon",
                "minLiquidity": min_liquidity,
                "sortBy": sorted_by,
                "sortDirection": sort_direction,
                "limit": limit,
                "minApy": min_apy,
                "maxApy": max_apy
            },
            headers={"Authorization": "Bearer " + self.api_key}
        ).content

        tokens = json.loads(requested_content)["tokens"]
        token_data = [
            PortalsTokenData(
                token["name"],
                token["symbol"],
                token["address"],
                token["platform"],
                float(token["price"]),
                float(token["liquidity"]),
                PortalsMetric(
                    float(token["metrics"]["apy"]),
                    float(token["metrics"]["baseApy"]),
                    float(token["metrics"]["volumeUsd1d"]),
                    float(token["metrics"]["volumeUsd7d"])
                )
            )
            for token in tokens
        ]

        return token_data
    
    def _proccess_yield_data(self, yields: List[PortalsTokenData]) -> List[PortalsTokenData]:
        yields = sorted(yields, key=lambda t: t.metrics.apy, reverse=True)
        filtered_yields = [dataclasses.asdict(yield_data) for yield_data in yields if yield_data.metrics.volume_usd_7d > 0]

        return filtered_yields[:self.top_k]
        

    def find_yields(self, wallet_address: str, yield_config: PortalsYieldConfig) -> dict:
        token_balances = self.find_top_k_balances(wallet_address)

        token_yield_map = {}

        # Find yields for each token
        for i in range(self.top_k):
            yield_data = self.get_token_data(
                search_token_symbols=[token_balances[i].symbol],
                min_apy=yield_config.min_apy,
                max_apy=yield_config.max_apy,
                min_liquidity=yield_config.min_liquidity
            )
            filtered_yields = self._proccess_yield_data(yield_data)

            token_yield_map[token_balances[i].symbol] = filtered_yields
                
        # Find yields for all of the tokens
        top_k_tokens = [token_balances[i].symbol for i in range(self.top_k)]
        yield_data = self.get_token_data(
            search_token_symbols=top_k_tokens, 
            min_apy=yield_config.min_apy, 
            max_apy=yield_config.max_apy
        )
        filtered_yields = self._proccess_yield_data(yield_data)

        token_yield_map["_".join(top_k_tokens)] = filtered_yields

        return token_yield_map

    def find_top_k_balances(self, wallet_address) -> List[PortalTokenInfo]:
        token_balances = self.get_wallet_balance(wallet_address)
        token_balances = sorted(token_balances, key=lambda t: t.balance_usd, reverse=True)

        return token_balances[:self.top_k]
