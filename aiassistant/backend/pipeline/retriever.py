import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import gc

class HybridRetriever:
    def __init__(self):
        # We use a simple TF-IDF vectorizer instead of SentenceTransformers
        # to eliminate Hugging Face dependencies and save RAM.
        self.vectorizer = TfidfVectorizer(stop_words='english')
        self.documents = []
        self.tfidf_matrix = None
        
    def ingest(self, chunks):
        if not chunks:
            return
        
        print(f"[Retriever] Ingesting {len(chunks)} chunks using TF-IDF...")
        
        # Add new chunks to the existing document list
        self.documents.extend(chunks)
        
        try:
            # Re-fit the vectorizer and transform all documents
            # (TF-IDF is fast enough to do this on the fly for academic documents)
            self.tfidf_matrix = self.vectorizer.fit_transform(self.documents)
            print(f"[Retriever] Ingestion complete. Index size: {len(self.documents)}")
        except Exception as e:
            print(f"[Retriever] Ingestion failed: {e}")
        finally:
            gc.collect()
        
    def retrieve(self, query, top_k=3):
        if not self.documents or self.tfidf_matrix is None:
            return []
        
        try:
            # Transform the query into the same TF-IDF space
            query_vec = self.vectorizer.transform([query])
            
            # Calculate cosine similarity between query and all documents
            similarities = cosine_similarity(query_vec, self.tfidf_matrix).flatten()
            
            # Get top_k indices
            top_indices = similarities.argsort()[-top_k:][::-1]
            
            results = []
            for idx in top_indices:
                if similarities[idx] > 0:  # Only return relevant results
                    results.append({
                        "chunk": self.documents[idx],
                        "score": float(similarities[idx])
                    })
            return results
        except Exception as e:
            print(f"[Retriever] Retrieval failed: {e}")
            return []

# Singleton memory-based retriever
retriever_instance = HybridRetriever()

def get_context(query, document_id=None):
    """
    Finds the most relevant context from the uploaded documents using TF-IDF.
    Completely local, no external APIs or heavy models used.
    """
    results = retriever_instance.retrieve(query)
    if not results:
        return ""
    
    context = "\n\n".join([r['chunk'] for r in results])
    return context
