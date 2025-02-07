from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings

class MiniLmEmbeddingService:
    def __init__(self) -> None:
        load_dotenv()
        self.model_name = "sentence-transformers/all-MiniLM-L6-v2"
        self.model_kwargs = {'device': 'cpu'}
        self.encode_kwargs = {'normalize_embeddings': False}
        
    def get_service(self) -> HuggingFaceEmbeddings:
        return HuggingFaceEmbeddings(
            model_name=self.model_name,
            model_kwargs=self.model_kwargs,
            encode_kwargs=self.encode_kwargs
        )