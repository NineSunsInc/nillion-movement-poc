# Standard library imports
from typing import Any

# Third-party imports
from dotenv import load_dotenv
from langchain.globals import set_debug
from langchain.storage import InMemoryStore
from langgraph.checkpoint.memory import MemorySaver
from sentence_transformers import CrossEncoder

# Local application imports
from agent_modules.database.repositories.embedding_repository import EmbeddingRepository
from agent_modules.database.repositories.opensearch_repository import OpenSearchRepository
from agent_modules.database.types.agent import Agent
from agent_modules.database.const.prompt import *
from agent_modules.database.const.models import NILLION_MODEL, TEMPERATURE, AGENT_MODEL
from agent_modules.agent.tools import *
from agent_modules.factory.llm_factory import LLMFactory, LLMConfig
from agent_modules.factory.node_factory import NodeFactory, NodeFactoryConfig

class AgentBuilder:
    """Builder class for constructing the agent"""
    
    def __init__(
        self,
        user_store: InMemoryStore,
        memory: MemorySaver,
        user_data_embedding_repository: EmbeddingRepository,
        opensearch_repository: OpenSearchRepository,
        cross_encoder: CrossEncoder,
        debug: bool = False
    ):
        load_dotenv()
        if (debug):
            set_debug(True)

        self.user_store = user_store
        self.memory = memory
        self.debug = debug

        self.user_data_embedding_repository = user_data_embedding_repository
        self.opensearch_repository = opensearch_repository
        self.cross_encoder = cross_encoder

        self.llm_factory = LLMFactory()
        self._initialize_llms()
        
    def _initialize_llms(self):
        """Initialize LLM models"""
        ai_provider = os.getenv("AI_PROVIDER", "groq")
        self.provided_llm = self.llm_factory.create_llm(
            ai_provider,
            LLMConfig(temperature=TEMPERATURE)
        )

        if os.getenv("LLAMA_PROVIDER", "ollama") == "ollama":
            self.llama_llm = self.llm_factory.create_llm(
                "ollama",
                LLMConfig(model=AGENT_MODEL, temperature=TEMPERATURE)
            )
        elif os.getenv("LLAMA_PROVIDER", "nillion") == "nillion":
            self.llama_llm = self.llm_factory.create_llm(
                "nillion",
                LLMConfig(model=NILLION_MODEL, temperature=TEMPERATURE)
            )
        else:
            raise ValueError(f"Invalid LLM provider: {os.getenv('LLAMA_PROVIDER')}")
    
    def build(self) -> Any:
        """Build and return the complete agent"""
        node_factory = NodeFactory(
            NodeFactoryConfig(
                llama_llm=self.llama_llm,
                provided_llm=self.provided_llm,
                user_store=self.user_store,
                user_data_embedding_repository=self.user_data_embedding_repository,
                opensearch_repository=self.opensearch_repository,
                cross_encoder=self.cross_encoder
            )
        )
        
        executor_nodes = node_factory.create_executor_nodes()
        agent_nodes = node_factory.create_agent_nodes(list(executor_nodes.keys()))
        rag_nodes = node_factory.create_rag_nodes()
        
        agent = Agent(**{**executor_nodes, **agent_nodes, **rag_nodes})
        return agent.compile_graph(self.user_store, self.memory)
    
