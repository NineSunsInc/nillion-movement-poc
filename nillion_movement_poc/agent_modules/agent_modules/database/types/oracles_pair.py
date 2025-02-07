from dataclasses import dataclass


@dataclass
class OraclesPair:
    pair: tuple
    contract_address: str