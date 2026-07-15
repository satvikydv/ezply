import faiss
import numpy as np
from sentence_transformers import SentenceTransformer


class EmbeddingService:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        # Load lightweight model suitable for CPU local embeddings
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()
        
    def embed_text(self, text: str) -> np.ndarray:
        """Embed a single text string."""
        return self.model.encode(text, normalize_embeddings=True)

    def compute_similarity(self, embed1: np.ndarray, embed2: np.ndarray) -> float:
        """Compute cosine similarity between two normalized embeddings."""
        # Since normalize_embeddings=True, inner product is cosine similarity
        return float(np.dot(embed1, embed2))

    def create_faiss_index(self) -> faiss.IndexFlatIP:
        """Create a new FAISS index for inner product (cosine sim on normalized vectors)."""
        return faiss.IndexFlatIP(self.dimension)

    def embed_job(self, title: str, description: str) -> np.ndarray:
        """Embed a job using its title and description truncated to ~2000 chars."""
        # Truncate description to roughly 2000 characters
        trunc_desc = description[:2000] if description else ""
        text = f"Title: {title}\nDescription: {trunc_desc}"
        return self.embed_text(text)

    def embed_resume(self, resume_text: str) -> np.ndarray:
        """Embed the user's resume."""
        return self.embed_text(resume_text)


# Singleton instance
embedding_service = EmbeddingService()
