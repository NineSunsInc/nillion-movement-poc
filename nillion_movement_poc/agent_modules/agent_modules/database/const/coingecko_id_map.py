from typing import Dict, List
import os
import json
from datetime import datetime, timedelta
from difflib import get_close_matches
import requests

# Constants for caching and prioritization.
CACHE_FILE = os.path.join(os.path.dirname(__file__), "coingecko_token_cache.json")
CACHE_DURATION = timedelta(days=1)
PRIORITIZED_ECOSYSTEMS = [
    "polygon", "movement labs", "0g", "nillion", "arbitrum",
    "bitcoin", "ethereum", "aptos", "sui", "binance smart chain"
]

class CoinGeckoCacheManager:
    """
    This class manages the token list cache.
    It reads from (or refreshes) the local file that caches the full token list
    from CoinGecko (queried from the /coins/list endpoint).
    """
    def __init__(self, cache_file: str = CACHE_FILE, cache_duration: timedelta = CACHE_DURATION):
        self.cache_file = cache_file
        self.cache_duration = cache_duration
        self.token_list = self.load_token_list()

    def load_token_list(self):
        """
        Load the token list from the cache file if it exists and is fresh.
        Otherwise query CoinGecko and update the cache file.
        """
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    data = json.load(f)
                timestamp = datetime.fromisoformat(data.get("timestamp"))
                if datetime.now() - timestamp < self.cache_duration:
                    return data.get("token_list", [])
            except Exception as e:
                print(f"Error reading cache file: {e}")

        # Otherwise, fetch new data.
        return self.fetch_and_cache_token_list()

    def fetch_and_cache_token_list(self):
        """
        Query the CoinGecko /coins/list endpoint and save result to cache.
        """
        url = "https://api.coingecko.com/api/v3/coins/list"
        try:
            response = requests.get(url)
            response.raise_for_status()
            token_list = response.json()
            data = {
                "timestamp": datetime.now().isoformat(),
                "token_list": token_list
            }
            with open(self.cache_file, "w") as f:
                json.dump(data, f)
            return token_list
        except Exception as e:
            raise Exception(f"Failed to fetch token list from CoinGecko: {e}")

    def lookup_token(self, query: str, cutoff: float = 0.6):
        """
        Given a query string, return a list of matching tokens from the token list.
        The match is performed on a combined string of token name and symbol.
        If no results are found via fuzzy matching (using an adjusted cutoff based
        on query length), then a simple substring search is attempted.
        """
        token_strings = [
            f"{token['name']} ({token['symbol']})" for token in self.token_list
        ]
        # If query is short, lower the cutoff value to be more permissive.
        effective_cutoff = cutoff if len(query) >= 4 else 0.3
        matches = get_close_matches(query, token_strings, n=5, cutoff=effective_cutoff)
        if not matches:
            # Fallback: try a simple substring search (case-insensitive)
            substring_matches = [
                token for token in self.token_list
                if query.lower() in token['name'].lower() or query.lower() in token['symbol'].lower()
            ]
            if substring_matches:
                return substring_matches
            else:
                return None

        result = []
        for match in matches:
            if "(" in match and ")" in match:
                symbol = match.split("(")[-1].rstrip(")")
            else:
                symbol = match.lower()
            for token in self.token_list:
                if token['symbol'].lower() == symbol.lower():
                    result.append(token)
                    break
        return result

    def prioritize_tokens(self, tokens):
        """
        Reorder the token list so that tokens from our prioritized ecosystems come first.
        """
        if not tokens:
            return tokens

        prioritized = []
        others = []
        for token in tokens:
            token_name = token.get("name", "").lower()
            token_symbol = token.get("symbol", "").lower()
            if any(ecosystem in token_name or ecosystem in token_symbol for ecosystem in PRIORITIZED_ECOSYSTEMS):
                prioritized.append(token)
            else:
                others.append(token)
        return prioritized + others

class TokenInfo:
    def __init__(self, coingecko_id: str, variants: List[str]):
        self.coingecko_id = coingecko_id
        self.variants = variants

# Extended static mapping to quickly resolve common tokens.
TOKEN_TYPES_TO_COINGECKO_ID: Dict[str, TokenInfo] = {
    "eth": TokenInfo("ethereum", ["ethereum", "ether"]),
    "usdc": TokenInfo("bridged-usdc", ["usdc", "usd coin"]),
    "usdt": TokenInfo("bridged-usdt", ["tether", "usdt"]),
    "btc": TokenInfo("bitcoin", ["bitcoin"]),
    "move": TokenInfo("movement", ["movement"]),
    "pol": TokenInfo("polygon-ecosystem-token", ["polygon", "polygon token"]),
    "xlm": TokenInfo("stellar", ["stellar", "xlm"]),
    "arb": TokenInfo("arbitrum", ["arbitrum"]),
    "avax": TokenInfo("avalanche-2", ["avalanche"]),
    "wbtc": TokenInfo("bridged-wbtc", ["wrapped bitcoin", "wrapped btc"]),
    "dai": TokenInfo("dai", ["dai stablecoin"]),
    "apt": TokenInfo("aptos", ["aptos", "apt"]),
    "weth": TokenInfo("weth", ["wrapped ethereum", "wrapped eth"]),
    "sui": TokenInfo("sui", ["sui"]),
    "matic": TokenInfo("matic-network", ["polygon", "matic", "polygon network"]),
    "bnb": TokenInfo("binancecoin", ["bnb", "binance coin", "bnb chain", "bnb smart chain", "binance smart chain"]),
}

def get_token_info(token_query: str):
    """
    Look up token info given a query string. Returns:
      - A single token (dict) if the match is unambiguous.
      - A list of candidate tokens (list of dict) if multiple similar matches are found.
      - None if no match was found.
    The function first checks the static mapping and, if not found, falls back to a fuzzy search
    of the dynamic token list.
    """
    token_query_norm = token_query.lower().strip()

    # First, try to match against our static mapping.
    for key, token_data in TOKEN_TYPES_TO_COINGECKO_ID.items():
        if token_query_norm == key or token_query_norm in [v.lower() for v in token_data.variants]:
            return {
                "id": token_data.coingecko_id,
                "symbol": key,
                "name": token_data.variants[0] if token_data.variants else key
            }

    # Fallback to fuzzy searching the dynamic token list.
    manager = CoinGeckoCacheManager()
    tokens = manager.lookup_token(token_query)
    if tokens:
        tokens = manager.prioritize_tokens(tokens)
        if len(tokens) == 1:
            return tokens[0]
        else:
            return tokens  # Ambiguous result: caller may ask the user for more clarity.
    return None

# For quick testing without the rest of the system.
if __name__ == "__main__":
    test_queries = [
        # "bitcoin", "eth", "aptos", "bnb", "usd coin", "wrapped ethereum",
        "movement", "plum", "plu"  # Try partial queries for robustness.
    ]
    for q in test_queries:
        result = get_token_info(q)
        print(f"Query: {q}")
        if result is None:
            print("  No match found.")
        elif isinstance(result, list):
            print("  Multiple matches found:")
            for token in result:
                print(f"    {token['name']} ({token['symbol']}) -> id: {token['id']}")
        else:
            print(f"  Found: {result['name']} ({result['symbol']}) -> id: {result['id']}")