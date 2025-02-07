# Standard library imports
import os
from typing import Dict
import uuid
import time

# Third-party imports
from agent_modules.database.repositories.opensearch_repository import OpenSearchRepository
import chainlit as cl
from dishka import Container
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import MemorySaver

# Local application imports
from agent_modules.agent.agent_builder import AgentBuilder
from agent_modules.database.const.chain_config import ChainConfig
from agent_modules.database.types.network_config import NetworkConfig
from agent_modules.database.repositories.embedding_repository import EmbeddingRepository
from agent_modules.factory.service_factory import BlockchainServiceFactory
from agent_modules.chat.data_service import DataService
from dotenv import load_dotenv
from sentence_transformers import CrossEncoder

class ChatApplication:
    def __init__(self, dependency_container: Container):
        self.data_service = DataService()
        self.dependency_container = dependency_container
        self.user_data_embedding_repository = dependency_container.get(EmbeddingRepository)

    async def initialize_chat_agent(self):
        # Set up memory
        memory = MemorySaver()

        # Ask user actions
        raw_data = await self._get_user_data()
        chain_option = await self._get_chain_option()

        # Setup user's data
        user_data = await self._setup_user_data(chain_option, raw_data)

        app = self._build_agent(user_data, memory)
        await self._initialize_session(app, chain_option, memory)

    async def _get_user_data(self):
        load_dotenv()

        while True:
            env_data_api_key = os.getenv("DATA_API_KEY")

            user_data_api_key = {"output": env_data_api_key} if env_data_api_key else await cl.AskUserMessage(content="What is your Nine Suns Data API key?", timeout=30).send()
            if (user_data_api_key):
                await cl.Message(
                    content=f"Your Data API key is: {user_data_api_key['output']}",
                ).send()
                
                try:
                    raw_data = await self.data_service.get_and_decrypt_data(user_data_api_key['output'])
                    break
                except Exception as e:
                    print(e)
                    if (user_data_api_key['output'][:4] != "DATA"):
                        await cl.Message(
                            content=f"Wrong API Key format, make sure your data API key begins with \"DATA.<remaining_part>\"",
                        ).send()
                    else:
                        await cl.Message(
                            content="Please check your data API key again. I can't get any data from this key."
                        ).send()

            else:
                await cl.Message(
                    content=f"Please input your Nine Suns data API Key",
                ).send()
        
        # Store the user data only once
        # TODO: Create hash for the user data to know if we need to recreate the embedding table
        exists = self.user_data_embedding_repository.get_max_id()
        if exists == 0:
            self.user_data_embedding_repository.insert_text(text=raw_data, is_json_data=True)

        return raw_data

    async def _get_chain_option(self):
        env = await cl.AskActionMessage(
            content="Choose your working environment",
            actions=[
                cl.Action(
                    name=ChainConfig.NETWORKS[key].name, 
                    payload={"network_name": key}, 
                    label=ChainConfig.NETWORKS[key].name
                ) for key in ChainConfig.NETWORKS.keys()
            ]
        ).send()
        
        # Access the network_name from the payload
        network_name = env["payload"]["network_name"]
        return ChainConfig.get_network_config(network_name)
    
    async def _setup_user_data(self, chain_option, raw_data):
        wallet_public_key = None
        wallet_private_key = None
        ask_user = False

        public_key_dict_key = f"{chain_option.config_keys[1]}_public_key"
        private_key_dict_key = f"{chain_option.config_keys[1]}_private_key"

        if (chain_option.network_id not in ["PORTO", "APTOS", "MEVM", "POLYGON_AMOY", "ETH_SEPOLIA", "ARBITRUM_SEPOLIA", "ARBITRUM_ONE", "POLYGON_POS"]):
            raise Exception("Unsupported chain")

        wallets = [blockchain for blockchain in raw_data['blockchains'] if (blockchain['type'] == "CRYPTO_WALLET")]
        if (wallets is None or len(wallets) == 0):
            ask_user = True
        
        keys = raw_data["credentials"]
        if (keys is None or len(keys) == 0):
            ask_user = True


        # TODO: This is for the demo 2024/11/12
        if (chain_option.network_id == "POLYGON_POS"):
            wallet_public_key = "0x52A258ED593C793251a89bfd36caE158EE9fC4F8"
            wallet_private_key = "0x..."

        if (chain_option.network_id == "ARBITRUM_ONE"):
            wallet_public_key = "0x8626f6940E2eb28930eFb4CeF49B2d1F2C9C1199"
            wallet_private_key = "0xdf57089febbacf7ba0bc227dafbffa9fc08a93fdc68e1e42411a14efcf23656e"

        # Check the env and get the related private key.
        if (not ask_user):
            for wallet in wallets:
                if (wallet['value']["network"] == chain_option.config_keys[0]):
                    key_name = wallet['value']["key"]
                    for key in keys:
                        if (key["type"] == "Keys" and key['value']['name'] == key_name):
                            wallet_public_key = wallet['value']['address']
                            wallet_private_key = key['value']['privateKey']

        # Ask the user about network's public and private key if cannot find
        if (ask_user or wallet_public_key is None or wallet_private_key is None):
            if (wallet_private_key is None):
                provided_private_key = await cl.AskUserMessage(content=f"What is your wallet private key on {chain_option.config_keys[0]}?", timeout=120).send()
                if (provided_private_key):
                    wallet_private_key = provided_private_key.get("output")
                else:
                    # Handle exception here
                    pass
            if (wallet_public_key is None):
                provided_public_key = await cl.AskUserMessage(content=f"What is your wallet public key on {chain_option.config_keys[0]}?", timeout=120).send()
                if (provided_public_key):
                    wallet_public_key = provided_public_key.get("output")
                else:
                    # Handle exception here
                    pass

        user_data = {
            private_key_dict_key: wallet_private_key,
            public_key_dict_key: wallet_public_key,
            "network_env": chain_option.network_id
        }

        blockchain_service = BlockchainServiceFactory.create_service(chain_option.network_id, chain_option, wallet_private_key)
        available_tokens = await blockchain_service.retrieve_available_tokens(wallet_public_key)
        
        user_data["available_tokens"] = available_tokens
        user_data["blockchain_service"] = blockchain_service

        return user_data

    def _build_agent(self, user_data, memory):
        # Create the user's store
        namespace = ("users", "1") # Fixed user id to "1" because we only test this locally
        
        user_store = InMemoryStore()
        user_store.put(namespace, "user_data", user_data)

        # Create and compile the agent graph
        app = AgentBuilder(
            user_store=user_store,
            memory=memory,
            user_data_embedding_repository=self.dependency_container.get(EmbeddingRepository),
            opensearch_repository=self.dependency_container.get(OpenSearchRepository),
            cross_encoder=self.dependency_container.get(CrossEncoder),
        ).build()

        # Draw agent's graph
        # self._draw_agent_graph(app)

        return app

    def _draw_agent_graph(self, app):
        # Draw the architecture diagram
        from IPython.display import Image, display

        b_img = Image(app.get_graph(xray=True).draw_mermaid_png())
        display(b_img)

        # Store the architecture as an image
        with open("AgentArch.png", "wb") as agent_arch:
            agent_arch.write(b_img.data)

    async def _initialize_session(self, app, chain_option: NetworkConfig, memory):
        # Store the agent compiled graph to the user session
        network_key = next(key for key, config in ChainConfig.NETWORKS.items() 
                      if config.network_id == chain_option.network_id)
        
        cl.user_session.set("app_graph", app)
        cl.user_session.set("uuid", uuid.uuid4())
        cl.user_session.set("memory", memory)
        cl.user_session.set("current_chain", network_key)
        cl.user_session.set("explorer_config", chain_option.explorer)

        await cl.Message(
            content=f"You can now proceed with more actions on {chain_option.name}",
        ).send()