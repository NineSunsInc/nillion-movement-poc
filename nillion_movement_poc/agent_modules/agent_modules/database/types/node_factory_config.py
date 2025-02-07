from langchain_core.language_models import BaseChatModel
from dataclasses import dataclass
from sentence_transformers import CrossEncoder

from agent_modules.database.repositories.embedding_repository import EmbeddingRepository
from agent_modules.database.repositories.opensearch_repository import OpenSearchRepository

@dataclass
class NodeFactoryConfig:
    llama_llm: BaseChatModel
    provided_llm: BaseChatModel
    user_data_embedding_repository: EmbeddingRepository
    opensearch_repository: OpenSearchRepository
    user_store: any
    cross_encoder: CrossEncoder