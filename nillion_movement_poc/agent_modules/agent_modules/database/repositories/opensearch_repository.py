from enum import Enum
from agent_modules.opensearch.opensearch_service import OpenSearchService
from agent_modules.database.types.search_result import SearchResult

class SearchType(Enum):
    HYBRID = "hybrid"
    VECTOR = "vector"
    KEYWORD = "keyword"

class OpenSearchRepository:
    def __init__(self, index_name: str, opensearch_service: OpenSearchService = None):
        self.opensearch_service = opensearch_service if opensearch_service else OpenSearchService()
        self.index_name = index_name

    def search(self, query: str, search_type: SearchType) -> list[SearchResult]:
        if search_type == SearchType.HYBRID:
            return self.opensearch_service.hybrid_search(query, self.index_name)
        elif search_type == SearchType.VECTOR:
            return self.opensearch_service.vector_search(query, self.index_name)
        elif search_type == SearchType.KEYWORD:
            return self.opensearch_service.keyword_search(query, self.index_name)