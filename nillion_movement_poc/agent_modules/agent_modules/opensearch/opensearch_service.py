import uuid

from typing import Any, Dict
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk
from nltk.corpus import stopwords

from agent_modules.embedding.embedding_service import MiniLmEmbeddingService
from agent_modules.database.types.search_result import SearchResult

class OpenSearchService:
    def __init__(
            self,
            embedding_service: MiniLmEmbeddingService = None,
        ):
        """Initialize the OpenSearchService with default settings and configurations."""
        self.host = "localhost"
        self.port = 9200
        self.username = "admin"
        self.password = "admin"
        self.embeddings = embedding_service if embedding_service else MiniLmEmbeddingService().get_service()
        self.rrf_k = 5
        self.top_k = 20
        self.client = self._get_opensearch_client()
        self.bm25_threshold = 2.5
        self.custom_stopwords = set(["what", "where", "when", "why", "how"] + stopwords.words('english'))

    def _default_text_mapping(
        self,
        dim: int,
        engine: str = "nmslib",
        space_type: str = "l2",
        ef_search: int = 512,
        ef_construction: int = 512,
        m: int = 16,
        vector_field: str = "vector_field",
        text_field: str = "text",
        source_field: str = "source",
    ) -> Dict[str, Any]:
        """For Approximate k-NN Search, this is the default mapping to create index."""
        return {
            "settings": {"index": {"knn": True, "knn.algo_param.ef_search": ef_search}},
            "mappings": {
                "properties": {
                    vector_field: {
                        "type": "knn_vector",
                        "dimension": dim,
                        "method": {
                            "name": "hnsw",
                            "space_type": space_type,
                            "engine": engine,
                            "parameters": {"ef_construction": ef_construction, "m": m},
                        },
                    },
                    text_field: {"type": "text", "analyzer": "english"},
                    source_field: {"type": "text", "analyzer": "english"},
                }
            },
        }

    def _create_index(self, index_name: str, mapping: Dict[str, Any]):
        """Create an index in OpenSearch with the given name and mapping if it does not already exist."""
        try:
            self.client.indices.get(index=index_name)
        except Exception as e:
            print(e)
            self.client.indices.create(index=index_name, body=mapping)  

    def _get_opensearch_client(self):
        """Get the OpenSearch client with the configured settings."""
        return OpenSearch(
            hosts=[{'host': self.host, 'port': self.port}],
            http_compress=True,
            http_auth=(self.username, self.password),
            use_ssl=False,
            verify_certs=False,
            ssl_context=None,
        )

    def bulk_insert_texts(self, texts: list[str], sources: list[str], index_name: str, text_field: str, vector_field: str, source_field: str):
        """Insert multiple texts into the OpenSearch index in bulk."""
        embeddings = self.embeddings.embed_documents(texts)
        requests = []
        return_ids = []
        mapping = self._default_text_mapping(len(embeddings[0]), vector_field=vector_field, text_field=text_field, source_field=source_field)

        # Create index if not exists
        self._create_index(index_name, mapping)

        for i, text in enumerate(texts):
            _id = uuid.uuid4()
            request = {
                "_id": _id,
                "_op_type": "index",
                "_index": index_name,
                vector_field: embeddings[i],
                text_field: text,
                source_field: sources[i]
            }
            requests.append(request)
            return_ids.append(_id)

        bulk(self.client, requests)
        self.client.indices.refresh(index=index_name)
        return return_ids

    def keyword_search(self, query: str, index_name: str, minimum_should_match: str = "80%", debug_mode: bool = False) -> list[SearchResult]:
        """Perform a keyword search on the given index with the provided query."""
        # Split query into words for creating boolean clauses 
        words = set(query.split())
        clauses = [{"match": {"text": {"query": word, "_name": f"should-{word}", "analyzer": "english"}}} for word in words if word.lower() not in self.custom_stopwords]

        result = self.client.search(
            index=index_name, 
            body={
                "from": 0,
                "size": self.top_k,
                "query": {
                    "bool": {
                        "should": clauses,
                        "minimum_should_match": minimum_should_match
                    }
                },
                "highlight": {
                    "fields": {
                        "text": {}  # Specify the field to highlight
                    },
                    "pre_tags": ["<em>"],  # Tag to use before the highlighted text
                    "post_tags": ["</em>"]  # Tag to use after the highlighted text
                }
            })

        # Print the highlighted text
        if debug_mode:
            print("Search Clause: ", clauses)
            for hit in result['hits']['hits']:
                print("Document ID:", hit['_id'])
                print("Source:", hit["_source"]["source"])
                if 'highlight' in hit:
                    print("Highlighted Text:", hit['highlight']['text'])
                if "matched_queries" in hit:
                    print("Matched Queries:", hit["matched_queries"])
                if "_score" in hit:
                    print("Score:", hit["_score"])
                else:
                    print("No highlights found.")
            print("--------------------------------")

        return [SearchResult(id=hit["_id"], text=hit["_source"]["text"], score=hit["_score"], source=hit["_source"]["source"]) for hit in result["hits"]["hits"] if hit["_score"] > self.bm25_threshold]
    
    def vector_search(self, query: str, index_name: str) -> list[SearchResult]:
        """Perform a vector search on the given index with the provided query."""
        vec = self.embeddings.embed_query(query)
        result = self.client.search(index=index_name, body={"query": {"knn": {"vector": {"vector": vec, "k": self.top_k}}}})
        
        return [SearchResult(id=hit["_id"], text=hit["_source"]["text"], score=hit["_score"], source=hit["_source"]["source"]) for hit in result["hits"]["hits"]]
    
    def hybrid_search(self, query: str, index_name: str, minimum_should_match: str = "80%") -> list[SearchResult]:
        """Perform a hybrid search combining keyword and vector search results."""
        keyword_search_result = {hit.id: hit for hit in self.keyword_search(query, index_name, minimum_should_match)}
        vector_search_result = {hit.id: hit for hit in self.vector_search(query, index_name)}
        retrieved_results = {**keyword_search_result, **vector_search_result}
        retrieved_ids = set(retrieved_results.keys())

        keyword_search_rank = {result.id: i + 1 for i, result in enumerate(keyword_search_result.values())}
        vector_search_rank = {result.id: i + 1 for i, result in enumerate(vector_search_result.values())}

        rrf_scores = {doc_id: score for doc_id in retrieved_ids if (score := self._calculate_rrf(doc_id, keyword_search_rank, vector_search_rank)) > 0}
        rrf_scores = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        sorted_results = [SearchResult(retrieved_results[doc_id].id, retrieved_results[doc_id].text, score, retrieved_results[doc_id].source) for doc_id, score in rrf_scores]

        return sorted_results
    
    def _calculate_rrf(self, doc_id: str, keyword_search_rank: dict, knn_search_rank: dict) -> float:
        """Calculate the Reciprocal Rank Fusion (RRF) score for a document."""
        score = 0
        score += 1.0 / (self.rrf_k + keyword_search_rank[doc_id]) if doc_id in keyword_search_rank else 0
        if score > 0:
            score += 1.0 / (self.rrf_k + knn_search_rank[doc_id]) if doc_id in knn_search_rank else 0
        return score
    
    def delete_index(self, index_name: str):
        """Delete the specified index from OpenSearch."""
        return self.client.indices.delete(index=index_name)
