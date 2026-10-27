import math
import re
from typing import List, Dict, Any, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from db import DatabaseManager

class PrecisionRetriever:
    """
    Precision-first RAG retriever:
    - Queries chunks directly from persistent storage (SQLite/Supabase)
    - Isolates chunks per user and per document
    - Combines TF-IDF vector similarity with exact term frequency and heading boosts
    - Evaluates evidence sufficiency and prevents unsupported hallucination
    """

    @staticmethod
    def retrieve(query: str, user_id: str, document_id: Optional[str] = None, 
                 top_k: int = 4, min_confidence_threshold: float = 0.08) -> Dict[str, Any]:
        """
        Retrieves relevant passages for a query.
        Returns:
            {
                "is_sufficient": bool,
                "confidence": float,
                "chunks": List[Dict],
                "combined_context": str,
                "citations": List[Dict]
            }
        """
        # Fetch candidate chunks from DB
        if document_id:
            raw_chunks = DatabaseManager.get_document_chunks(document_id, user_id)
        else:
            # If no document specified, fetch all documents belonging to user
            docs = DatabaseManager.get_documents_by_user(user_id)
            raw_chunks = []
            for d in docs[:10]: # search across recent 10 documents
                raw_chunks.extend(DatabaseManager.get_document_chunks(d["id"], user_id))

        if not raw_chunks:
            return {
                "is_sufficient": False,
                "confidence": 0.0,
                "chunks": [],
                "combined_context": "",
                "citations": []
            }

        texts = [c["chunk_text"] for c in raw_chunks]
        
        # Fit TF-IDF on candidate chunks
        try:
            vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2))
            tfidf_matrix = vectorizer.fit_transform(texts)
            query_vec = vectorizer.transform([query])
            sim_scores = cosine_similarity(query_vec, tfidf_matrix).flatten()
        except Exception:
            sim_scores = [0.0] * len(texts)

        # Keyword matching boost
        query_words = set(re.findall(r'\b[a-zA-Z0-9]{3,}\b', query.lower()))
        scored_candidates = []

        for idx, chunk in enumerate(raw_chunks):
            base_score = float(sim_scores[idx]) if idx < len(sim_scores) else 0.0
            chunk_lower = chunk["chunk_text"].lower()
            section_lower = (chunk.get("section_title") or "").lower()

            # Exact keyword overlap
            matched_words = sum(1 for w in query_words if w in chunk_lower)
            keyword_ratio = matched_words / max(1, len(query_words))

            # Heading match boost
            heading_boost = 0.15 if any(w in section_lower for w in query_words) else 0.0

            final_score = round((base_score * 0.6) + (keyword_ratio * 0.3) + heading_boost, 3)

            if final_score > 0.01:
                scored_candidates.append({
                    "id": chunk.get("id"),
                    "page_number": chunk.get("page_number", 1),
                    "section_title": chunk.get("section_title", "General"),
                    "chunk_text": chunk["chunk_text"],
                    "chunk_type": chunk.get("chunk_type", "text"),
                    "score": final_score
                })

        # Sort by score descending
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        top_chunks = scored_candidates[:top_k]

        if not top_chunks:
            return {
                "is_sufficient": False,
                "confidence": 0.0,
                "chunks": [],
                "combined_context": "",
                "citations": []
            }

        top_score = top_chunks[0]["score"]
        is_sufficient = top_score >= min_confidence_threshold

        # Format citations
        citations = []
        context_parts = []
        for c in top_chunks:
            snippet = c["chunk_text"][:200] + "..." if len(c["chunk_text"]) > 200 else c["chunk_text"]
            citations.append({
                "page": c["page_number"],
                "section": c["section_title"],
                "snippet": snippet,
                "score": c["score"]
            })
            context_parts.append(f"[Source Page {c['page_number']} | Section: {c['section_title']}]\n{c['chunk_text']}")

        return {
            "is_sufficient": is_sufficient,
            "confidence": round(min(1.0, top_score), 2),
            "chunks": top_chunks,
            "combined_context": "\n\n---\n\n".join(context_parts),
            "citations": citations
        }
