import requests
from agent_modules.database.const.coingecko_id_map import get_token_info

class CoinGeckoService:
    """
    Service class for querying CoinGecko pricing information based on a token query.
    Uses a static mapping to quickly resolve common tokens and falls back to fuzzy search if needed.
    """
    BASE_URL = "https://api.coingecko.com/api/v3"

    def check_single_token_price(self, token_query: str, currency: str = "usd"):
        """
        Check the price of a single token.
        If the static mapping or fuzzy search yields an ambiguous result, return it for clarification.
        Otherwise, query CoinGecko's /simple/price endpoint using the token id.

        Args:
            token_query (str): The token query string.
            currency (str): The fiat or crypto currency against which to get the price.

        Returns:
            dict: Contains either the price and coin id or an error/ambiguity message.
        """
        token_info = get_token_info(token_query)
        if token_info is None:
            return {"error": f"No matching token found for the query '{token_query}'."}
        if isinstance(token_info, list):
            # Ambiguous result
            return {
                "ambiguity": True,
                "candidates": token_info,
                "message": "Multiple tokens match your query. Please clarify."
            }
        coin_id = token_info.get("id")
        url = f"{self.BASE_URL}/simple/price"
        params = {"ids": coin_id, "vs_currencies": currency}
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            price = data.get(coin_id, {}).get(currency)
            if price is not None:
                return {"price": price, "coin_id": coin_id}
            else:
                return {"error": "Price not found in response", "response": data}
        except Exception as e:
            return {"error": "Failed to query CoinGecko", "exception": str(e)}

if __name__ == "__main__":
    service = CoinGeckoService()
    test_tokens = ["plum"]
    for token in test_tokens:
        print(f"Testing query: {token}")
        result = service.check_single_token_price(token)
        print(result)


# import os
# import requests

# from dotenv import load_dotenv

# from agent_modules.database.const.coingecko_id_map import TOKEN_TYPES_TO_COINGECKO_ID

# class CoinGeckoService:
#     def __init__(self):
#         load_dotenv()
#         self.api_key = os.getenv("COINGECKO_API_KEY")
#         self.base_url = "https://api.coingecko.com/api/v3"

#     def check_single_token_price(self, token_type: str) -> float:
#         # Convert input to lowercase for case-insensitive matching
#         token_type = token_type.lower().strip()
        
#         # Remove common words that might be in the query
#         token_type = token_type.replace('token', '').replace('coin', '').strip()
        
#         # Try to find the token in our mapping
#         coingecko_id = None
        
#         # First check if the token is directly in our mapping
#         if token_type in TOKEN_TYPES_TO_COINGECKO_ID:
#             coingecko_id = TOKEN_TYPES_TO_COINGECKO_ID[token_type].coingecko_id
#         else:
#             # If not found, check variants
#             for token_info in TOKEN_TYPES_TO_COINGECKO_ID.values():
#                 if any(variant.lower() in token_type or token_type in variant.lower() 
#                       for variant in token_info.variants):
#                     coingecko_id = token_info.coingecko_id
#                     break

#         if coingecko_id is None:
#             raise Exception(f"Token type '{token_type}' is not supported")

#         url = f"{self.base_url}/simple/price?ids={coingecko_id}&vs_currencies=usd"
#         response = requests.get(url)
#         data = response.json()

#         return {
#             "price": round(data[coingecko_id]["usd"], 2),
#             "currency": "USD"
#         }
    