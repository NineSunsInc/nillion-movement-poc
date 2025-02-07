from agent_modules.database.types.portals_type import PortalsYieldConfig

class PortalsYieldConfigGetter:
    CONFIGS = {
        "safe": PortalsYieldConfig(
            min_apy=1, 
            max_apy=8,
            min_liquidity=500000
        ),
        "moderate": PortalsYieldConfig(
            min_apy=8, 
            max_apy=49,
            min_liquidity=5000
        ),
        "high": PortalsYieldConfig(
            min_apy=49, 
            max_apy=200,
            min_liquidity=1000
        )
    }

    @classmethod
    def get_yield_config(cls, yield_type: str) -> PortalsYieldConfig:
        if yield_type.lower() not in cls.CONFIGS:
            raise ValueError(f"Unsupported yield type: {yield_type}")
        
        return cls.CONFIGS[yield_type.lower()]