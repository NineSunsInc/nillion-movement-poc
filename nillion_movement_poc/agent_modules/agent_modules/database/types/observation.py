from dataclasses import dataclass

@dataclass
class Observation:
    seconds_ago: int
    tick_cumulative: int
    seconds_per_liquidity_cumulative_x128: int