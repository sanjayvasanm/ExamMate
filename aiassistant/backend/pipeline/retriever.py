import gc

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class HybridRetriever:
    """Process-local TF-IDF index rebuilt from persisted, scoped chunks."""
    def __init__(self):
        self.vectorizer=TfidfVectorizer(stop_words="english")
        self.documents=[]
        self.tfidf_matrix=None

    def _rebuild(self):
        if not self.documents:
            self.tfidf_matrix = None
            return
        self.tfidf_matrix=self.vectorizer.fit_transform([x["text"] for x in self.documents])

    def ingest(self,chunks,user_id=None,document_id=None):
        records=[]
        for chunk in chunks or []:
            text=(chunk.get("text") or chunk.get("chunk") or "") if isinstance(chunk,dict) else str(chunk)
            if text.strip():
                chunk_user_id = chunk.get("user_id") if isinstance(chunk, dict) else None
                chunk_document_id = chunk.get("document_id") if isinstance(chunk, dict) else None
                records.append({
                    "text":text.strip(),
                    "user_id":str(user_id or chunk_user_id) if (user_id or chunk_user_id) else None,
                    "document_id":str(document_id or chunk_document_id) if (document_id or chunk_document_id) else None,
                })
        if not records:return
        existing={(x["user_id"], x["document_id"], x["text"]) for x in self.documents}
        self.documents.extend(x for x in records if (x["user_id"], x["document_id"], x["text"]) not in existing)
        try:self._rebuild()
        except Exception as exc:print(f"[Retriever] Ingestion failed: {exc}")
        finally:gc.collect()

    def sync(self, chunks, user_id=None, document_id=None):
        uid=str(user_id) if user_id else None
        did=str(document_id) if document_id else None
        self.documents=[x for x in self.documents if not (
            x["user_id"] == uid and (did is None or x["document_id"] == did)
        )]
        self.ingest(chunks, user_id=uid, document_id=did)

    def sync_records(self, records, user_id=None):
        uid = str(user_id) if user_id else None
        self.documents = [x for x in self.documents if x["user_id"] != uid]
        self.ingest(
            [
                {
                    "text": record.get("content", ""),
                    "user_id": uid,
                    "document_id": record.get("document_id"),
                }
                for record in records
            ],
            user_id=uid,
        )

    def retrieve(self,query,user_id=None,document_id=None,top_k=3):
        if not self.documents or self.tfidf_matrix is None:return []
        uid=str(user_id) if user_id else None; did=str(document_id) if document_id else None
        allowed=[i for i,x in enumerate(self.documents) if (uid is None or x["user_id"]==uid) and (did is None or x["document_id"]==did)]
        if not allowed:return []
        try:
            scores=cosine_similarity(self.vectorizer.transform([query]),self.tfidf_matrix[allowed]).flatten()
            top=scores.argsort()[-top_k:][::-1]
            return [{"chunk":self.documents[allowed[i]]["text"],"score":float(scores[i])} for i in top if scores[i]>0]
        except Exception as exc:print(f"[Retriever] Retrieval failed: {exc}");return []

retriever_instance=HybridRetriever()
def get_context(query,user_id=None,document_id=None):
    return "\n\n".join(x["chunk"] for x in retriever_instance.retrieve(query,user_id=user_id,document_id=document_id))
