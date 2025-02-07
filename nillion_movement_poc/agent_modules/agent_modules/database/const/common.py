# This can be dynamically maintained by Mighty
# TODO: We should improve this to network, environment, then dexes, then tokens
token_contracts_move_ecosystem = {
    "USDC": "0x275f508689de8756169d1ee02d889c777de1cebda3a7bbcce63ba8a27c563c6f::tokens::USDC",
    "USDT": "0x275f508689de8756169d1ee02d889c777de1cebda3a7bbcce63ba8a27c563c6f::tokens::USDT",
    "WBTC": "0x275f508689de8756169d1ee02d889c777de1cebda3a7bbcce63ba8a27c563c6f::tokens::WBTC",
    "WETH": "0x275f508689de8756169d1ee02d889c777de1cebda3a7bbcce63ba8a27c563c6f::tokens::WETH",
    "MOVE": "0x1::aptos_coin::AptosCoin"
}

unit_to_factor = {
    "USDC": 10**6,
    "USDT": 10**6,
    "WBTC": 10**9,
    "WETH": 10**8,
    "MOVE": 10**8,
    "POL": 10**18,
    "SepoliaETH": 10**18
}

result_key_for_parser_type: dict = {
    "news": "news",
    "places": "places",
    "images": "images",
    "search": "organic",
}

token_type_to_address = {
    "ETH_SEPOLIA": {
        "WETH": "0xfff9976782d46cc05630d1f6ebab18b2324d6b14",
        "SepoliaETH": "0xfff9976782d46cc05630d1f6ebab18b2324d6b14",
        "USDC": "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",
        "UNI": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"
    }
}

UNISWAP_POOL_ABI_PATH = "modules/agent/resources/abis/uniswap_pool_abi.json"
ERC_20_TOKEN_ABI_PATH = "modules/agent/resources/abis/erc_20_abi.json"