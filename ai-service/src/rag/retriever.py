import os
import sys
from pathlib import Path
from typing import List, Dict, Any

# Ensure ai-service root is in sys.path
AI_SERVICE_DIR = Path(__file__).resolve().parent.parent.parent
if str(AI_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_DIR))

import chromadb
from src.rag.ingest import (
    CHROMA_PERSIST_DIR,
    COLLECTION_NAME,
    KNOWLEDGE_BASE_DIR,
    get_embedding_model,
)

def get_chroma_collection(persist_dir: Path = None):
    """Retrieves or connects to the persistent Chroma collection."""
    target_path = Path(persist_dir or CHROMA_PERSIST_DIR)

    # Auto-initialize if target is the default CHROMA_PERSIST_DIR and it doesn't exist yet
    if not target_path.exists():
        if (persist_dir is None or target_path.resolve() == CHROMA_PERSIST_DIR.resolve()) and KNOWLEDGE_BASE_DIR.exists():
            from src.rag.ingest import run_ingest
            run_ingest(kb_dir=KNOWLEDGE_BASE_DIR, persist_dir=target_path)
        else:
            return None

    try:
        client = chromadb.PersistentClient(path=str(target_path))
        try:
            collection = client.get_collection(name=COLLECTION_NAME)
        except Exception:
            if (persist_dir is None or target_path.resolve() == CHROMA_PERSIST_DIR.resolve()) and KNOWLEDGE_BASE_DIR.exists():
                from src.rag.ingest import run_ingest
                run_ingest(kb_dir=KNOWLEDGE_BASE_DIR, persist_dir=target_path)
                collection = client.get_collection(name=COLLECTION_NAME)
            else:
                return None
        return collection
    except Exception as err:
        print(f"[Warning] Chroma collection '{COLLECTION_NAME}' not found or unreachable: {err}")
        return None


def query_knowledge(query: str, k: int = 3, persist_dir: Path = None) -> List[Dict[str, Any]]:
    """
    Queries the knowledge base for semantic relevance.
    Accepts natural language query (Vietnamese or English) and returns top-k passage matches.
    Each match includes {id, title, source, snippet, score, doc_id, chunk_index}.
    """
    if not query or not query.strip():
        return []

    collection = get_chroma_collection(persist_dir)
    if collection is None:
        return []

    count = collection.count()
    if count == 0:
        return []

    # E5 model requires 'query: ' prefix for symmetric semantic retrieval
    model = get_embedding_model()
    query_text = f"query: {query.strip()}"
    query_emb = model.encode([query_text], normalize_embeddings=True, show_progress_bar=False).tolist()

    n_results = min(k, count)
    results = collection.query(
        query_embeddings=query_emb,
        n_results=n_results,
        include=["documents", "metadatas", "distances"]
    )

    formatted_matches = []
    if results and "ids" in results and results["ids"]:
        ids = results["ids"][0]
        docs = results["documents"][0] if "documents" in results else []
        metas = results["metadatas"][0] if "metadatas" in results else []
        dists = results["distances"][0] if "distances" in results else []

        for i in range(len(ids)):
            meta = metas[i] if i < len(metas) else {}
            dist = dists[i] if i < len(dists) else 1.0
            # For cosine distance, similarity = 1 - distance
            similarity = round(max(0.0, 1.0 - dist), 4)

            formatted_matches.append({
                "id": ids[i],
                "title": meta.get("title", ""),
                "source": meta.get("source", ""),
                "snippet": docs[i] if i < len(docs) else "",
                "score": similarity,
                "doc_id": meta.get("doc_id", ""),
                "chunk_index": meta.get("chunk_index", 0),
            })

    return formatted_matches
