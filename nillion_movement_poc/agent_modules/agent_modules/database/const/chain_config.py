from agent_modules.database.const.contract_name import ContractName
from agent_modules.database.types.contract_config import ContractConfig
from agent_modules.database.types.network_config import NetworkConfig, Web3NetworkConfig, ExplorerConfig

# for porto, the /txn/ is the txn hash while for evm its /tx/ on etherscan variants

# for movement's explorer it has ?network=mainnet, ?network=bardock+testnet, ?network=porto

class ChainConfig:
    NETWORKS = {
        "porto": NetworkConfig(
            name="Movement Labs Porto Testnet",
            network_id="PORTO",
            token_type="MOVE",
            rpc_url="https://aptos.testnet.porto.movementlabs.xyz/v1",
            config_keys=("Movement Porto Testnet", "aptos_wallet"),
            explorer=ExplorerConfig(
                base_url="https://explorer.testnet.porto.movementnetwork.xyz",
                transaction_path="txn",
                network_param="?network=testnet"
            )
        ),
        "aptos": NetworkConfig(
            name="Movement Labs Aptos Testnet",
            network_id="APTOS",
            token_type="MOVE",
            rpc_url="https://aptos.testnet.suzuka.movementlabs.xyz/v1",
            config_keys=("Movement Aptos Testnet", "aptos_wallet"),
            explorer=ExplorerConfig(
                base_url="",
                transaction_path="txn"
            )
        ),
        "mevm": Web3NetworkConfig(
            name="Movement Labs EVM Testnet",
            network_id="MEVM",
            token_type="MOVE",
            wrap_token_type="MOVE",
            rpc_url="https://mevm.devnet.imola.movementlabs.xyz",
            config_keys=("Movement MEVM Testnet", "mevm_wallet"),
            contract_map={},
            token_map={},
            explorer=ExplorerConfig(
                base_url="",
                transaction_path="tx"
            )
        ),
        "polygon_amoy": Web3NetworkConfig(
            name="Polygon Amoy Testnet",
            network_id="POLYGON_AMOY",
            token_type="POL",
            wrap_token_type="POL",
            rpc_url="https://rpc-amoy.polygon.technology",
            config_keys=("Polygon PoS Amoy - Testnet", "amoy_wallet"),
            contract_map={},
            token_map={},
            explorer=ExplorerConfig(
                base_url="https://amoy.polygonscan.com",
                transaction_path="tx"
            )
        ),
        "eth_sepolia": Web3NetworkConfig(
            name="Ethereum Sepolia Testnet",
            network_id="ETH_SEPOLIA",
            token_type="SepoliaETH",
            wrap_token_type="WETH",
            rpc_url="https://sepolia.gateway.tenderly.co",
            config_keys=("Ethereum Sepolia Testnet", "sepolia_wallet"),
            contract_map={
                ContractName.UNIVERSAL_ROUTER: ContractConfig("0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD", "modules/agent/resources/abis/universal_router_abi.json"),
                ContractName.UNISWAP_ROUTER_V2: ContractConfig("0xeE567Fe1712Faf6149d80dA1E6934E354124CfE3", "modules/agent/resources/abis/uniswap_routerv2_abi.json"),
                ContractName.UNISWAP_FACTORY_V3: ContractConfig("0x0227628f3F023bb0B980b67D528571c95c6DaC1c", "modules/agent/resources/abis/uniswap_factory_v3_abi.json"),
                ContractName.UNISWAP_PERMIT2: ContractConfig("0x000000000022D473030F116dDEE9F6B43aC78BA3", "modules/agent/resources/abis/uniswap_permit2_abi.json")
            },
            token_map={
                "WETH": "0xfff9976782d46cc05630d1f6ebab18b2324d6b14",
                "SepoliaETH": "0xfff9976782d46cc05630d1f6ebab18b2324d6b14",
                "USDC": "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",
                "UNI": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"
            },
            explorer=ExplorerConfig(
                base_url="https://sepolia.etherscan.io",
                transaction_path="tx"
            )
        ),
        "arbitrum_sepolia": Web3NetworkConfig(
            name="Arbitrum Sepolia Testnet",
            network_id="ARBITRUM_SEPOLIA",
            token_type="ETH",
            wrap_token_type="WETH",
            rpc_url="https://sepolia-rollup.arbitrum.io/rpc",
            config_keys=("Arbitrum Sepolia Testnet", "sepolia_wallet"),
            contract_map={
                ContractName.UNIVERSAL_ROUTER: ContractConfig("0x4A7b5Da61326A6379179b40d00F57E5bbDC962c2", "modules/agent/resources/abis/universal_router_abi.json"),
                ContractName.UNISWAP_ROUTER_V2: ContractConfig("0x101F443B4d1b059569D643917553c771E1b9663E", "modules/agent/resources/abis/uniswap_routerv2_abi.json"),
                ContractName.UNISWAP_FACTORY_V3: ContractConfig("0x248AB79Bbb9bC29bB72f7Cd42F17e054Fc40188e", "modules/agent/resources/abis/uniswap_factory_v3_abi.json"),
                ContractName.UNISWAP_PERMIT2: ContractConfig("0x000000000022D473030F116dDEE9F6B43aC78BA3", "modules/agent/resources/abis/uniswap_permit2_abi.json")
            },
            token_map={
                "WETH": "0x980B62Da83eFf3D4576C647993b0c1D7faf17c73",
                "USDC": "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",
            },
            explorer=ExplorerConfig(
                base_url="https://sepolia.arbiscan.io",
                transaction_path="tx"
            )
        ),
        "arbitrum_one": Web3NetworkConfig(
            name="Arbitrum One",
            network_id="ARBITRUM_ONE",
            token_type="ETH",
            wrap_token_type="WETH",
            rpc_url="http://127.0.0.1:8545",
            config_keys=("Arbitrum One", "one_wallet"),
            contract_map={
                ContractName.UNIVERSAL_ROUTER: ContractConfig("0x5E325eDA8064b456f4781070C0738d849c824258", "modules/agent/resources/abis/universal_router_abi.json"),
                ContractName.UNISWAP_FACTORY_V3: ContractConfig("0x1F98431c8aD98523631AE4a59f267346ea31F984", "modules/agent/resources/abis/uniswap_factory_v3_abi.json"),
                ContractName.UNISWAP_PERMIT2: ContractConfig("0x000000000022D473030F116dDEE9F6B43aC78BA3", "modules/agent/resources/abis/uniswap_permit2_abi.json")
            },
            token_map={
                "WETH": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
                "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
                "USDT": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
                "ARB": "0x912CE59144191C1204E64559FE8253a0e49E6548",
                "DAI": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1"
            },
            explorer=ExplorerConfig(
                base_url="https://arbiscan.io",
                transaction_path="tx"
            )
        ),
        "polygon_pos": Web3NetworkConfig(
            name="Polygon PoS Mainnet",
            network_id="POLYGON_POS",
            token_type="POL",
            wrap_token_type="POL",
            rpc_url="https://polygon.llamarpc.com",
            config_keys=("Polygon PoS Mainnet", "pos_wallet"),
            contract_map={},
            token_map={},
            explorer=ExplorerConfig(
                base_url="https://polygonscan.com",
                transaction_path="tx"
            )
        )
    }

    @classmethod
    def get_network_config(cls, chain_option: str) -> NetworkConfig:
        if chain_option not in cls.NETWORKS:
            raise ValueError(f"Unsupported chain: {chain_option}")
        return cls.NETWORKS[chain_option]