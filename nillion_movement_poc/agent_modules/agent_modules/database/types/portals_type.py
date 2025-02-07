from dataclasses import dataclass


# TODO: Naming these for better understanding
@dataclass
class PortalTokenInfo:
    symbol: str
    address: str
    balance_usd: float
    balance: float
    raw_balance: int

@dataclass(unsafe_hash=True, order=True)
class PortalsMetric:
    apy: float
    base_apy: float
    volume_usd_1d: float
    volume_usd_7d: float

@dataclass(unsafe_hash=True, order=True)
class PortalsTokenData:
    name: str
    symbol: str
    address: str
    platform: str
    price: float
    liquidity: float
    metrics: PortalsMetric

@dataclass 
class PortalsYieldConfig:
    min_apy: float
    max_apy: float
    min_liquidity: float
    # yield: float