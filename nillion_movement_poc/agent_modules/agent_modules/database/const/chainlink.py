from agent_modules.blockchain.services.oracles.chainlink_oracles import OraclesPair

CHAINLINK_FUNCTION_ABI_PATH = "agent/resources/abis/oracles_function_abi.json"

CHAINLINK_ORACLES_PAIR_ADDRESSES = [
    OraclesPair(("SepoliaETH", "USD"), "0x694AA1769357215DE4FAC081bf1f309aDC325306"),
    OraclesPair(("USDC", "USD"), "0xA2F78ab2355fe2f984D808B5CeE7FD0A93D5270E")
]