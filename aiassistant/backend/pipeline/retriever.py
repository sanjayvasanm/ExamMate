import numpy as np
import faiss

_model_instance = None

def get_embedding_model():
    global _model_instance
    if _model_instance is None:
        print("[AI] Initializing SentenceTransformer model...")
        from sentence_transformers import SentenceTransformer
        _model_instance = SentenceTransformer('all-MiniLM-L6-v2')
    return _model_instance

class HybridRetriever:
    def __init__(self):
        self.dimension = 384  # MiniLM dimension
        self.index = faiss.IndexFlatL2(self.dimension)
        self.documents = []
        
    def ingest(self, chunks):
        if not chunks:
            return
        # Lazy loading of model
        model = get_embedding_model()
        embeddings = model.encode(chunks)
        self.index.add(np.array(embeddings).astype("float32"))
        self.documents.extend(chunks)
        
    def retrieve(self, query, top_k=3):
        if self.index.ntotal == 0:
            return []
        # Lazy loading of model
        model = get_embedding_model()
        query_embedding = model.encode([query]).astype("float32")
        distances, indices = self.index.search(query_embedding, top_k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1 and idx < len(self.documents):
                results.append({
                    "chunk": self.documents[idx],
                    "score": float(distances[0][i])
                })
                
        return results

# Singleton memory-based fallback
retriever_instance = HybridRetriever()

def get_context(query, document_id=None):
    results = retriever_instance.retrieve(query)
    context = "\n\n".join([r['chunk'] for r in results])
    return context
