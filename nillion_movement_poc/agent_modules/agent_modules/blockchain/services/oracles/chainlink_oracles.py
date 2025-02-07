from typing import List

from agent_modules.blockchain.services.oracles.oracle_base import OraclesService
from agent_modules.database.const.chainlink import CHAINLINK_FUNCTION_ABI_PATH, CHAINLINK_ORACLES_PAIR_ADDRESSES
from agent_modules.database.types.oracles_pair import OraclesPair

class ChainLinkOracle(OraclesService):
    def __init__(self, w3, network_env) -> None:
        self.w3 = w3
        self.network_env = network_env
        self.supported_pair = {item.pair: item.contract_address for item in self._get_supported_oracles_pair()}

        with open(CHAINLINK_FUNCTION_ABI_PATH, 'r') as function_abi_file:
            self.function_abi = function_abi_file.read()

    def _get_supported_oracles_pair(self) -> List[OraclesPair]:
        return CHAINLINK_ORACLES_PAIR_ADDRESSES
    
    def _get_pair_contract_addresses(self, src_token, dest_token):
        if (src_token, dest_token) in self.supported_pair:
            return [self.supported_pair[(src_token, dest_token)]]

        # TODO: Return list of contracts to calculate the price of a pair (follow this: https://docs.chain.link/data-feeds/using-data-feeds#getting-a-different-price-denomination)
        elif (src_token == "SepoliaETH" and dest_token == "USDC"):
            return ["0x694AA1769357215DE4FAC081bf1f309aDC325306", "0xA2F78ab2355fe2f984D808B5CeE7FD0A93D5270E"]

        else:
            # TODO: We should find all possible combination before throwing this exception. 
            # For example A/B = ((A/C) / (D/C)) / (B/D)

            raise Exception("Unsupported traded pair")

    def calculate_pair_price(self, src_token, dest_token):
        reverse = False
        try:
            addresses = self._get_pair_contract_addresses(src_token, dest_token)
        except:
            addresses = self._get_pair_contract_addresses(dest_token, src_token)
            reverse = True

        prices = [self._get_pair_price(address) for address in addresses]

        final_price = None
        for price in prices:
            if not final_price:
                final_price = price
            else:
                final_price /= price

        return {
            "reverse": reverse,
            "price": final_price if not reverse else 1 / final_price
        } 

    def _get_pair_price(self, contract_address):
        contract = self.w3.eth.contract(address=contract_address, abi=self.function_abi)

        result = contract.functions.latestRoundData().call()
        price = result[1]

        return price
