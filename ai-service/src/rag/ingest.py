import os
import sys
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple
import yaml

# Ensure ai-service root is in sys.path
AI_SERVICE_DIR = Path(__file__).resolve().parent.parent.parent
if str(AI_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_DIR))

import chromadb
from sentence_transformers import SentenceTransformer

# Default Paths
KNOWLEDGE_BASE_DIR = Path(os.getenv("ECOTRACK_KB_DIR", AI_SERVICE_DIR / "knowledge_base"))
CHROMA_PERSIST_DIR = Path(os.getenv("ECOTRACK_CHROMA_DIR", AI_SERVICE_DIR / "data" / "chroma_db"))
COLLECTION_NAME = "energy_knowledge_base"
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"

_model = None


def get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")
    return _model


def parse_frontmatter(file_content: str) -> Tuple[Dict[str, Any], str]:
    """Extracts YAML frontmatter (title, source) and body from markdown."""
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, file_content, re.DOTALL)
    if match:
        meta_raw, body = match.groups()
        try:
            metadata = yaml.safe_load(meta_raw) or {}
        except Exception:
            metadata = {}
        return metadata, body.strip()
    return {}, file_content.strip()


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> List[str]:
    """
    Splits text into chunks of roughly ~500 tokens (approx 1200 chars) with overlap.
    Preserves paragraph or sentence boundaries where possible.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size
        if end >= text_len:
            chunks.append(text[start:].strip())
            break

        # Look for natural paragraph break first, then newline, then sentence period
        break_pos = text.rfind("\n\n", start, end)
        if break_pos == -1 or break_pos < start + (chunk_size // 2):
            break_pos = text.rfind("\n", start, end)
        if break_pos == -1 or break_pos < start + (chunk_size // 2):
            break_pos = text.rfind(". ", start, end)
            if break_pos != -1:
                break_pos += 1  # include period

        if break_pos == -1 or break_pos < start + (chunk_size // 2):
            break_pos = end

        chunk = text[start:break_pos].strip()
        if chunk:
            chunks.append(chunk)

        # Advance start with overlap
        start = max(start + 1, break_pos - overlap)

    return chunks


def load_documents_and_chunk(kb_dir: Path) -> List[Dict[str, Any]]:
    """Loads all markdown files in kb_dir, extracts frontmatter, and creates chunks."""
    if not kb_dir.exists():
        print(f"[Warning] Knowledge base directory does not exist: {kb_dir}")
        return []

    all_chunks = []
    md_files = sorted(list(kb_dir.glob("*.md")))
    print(f"[Ingest] Found {len(md_files)} markdown documents in {kb_dir}")

    for file_path in md_files:
        doc_id = file_path.stem
        content = file_path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)

        title = meta.get("title", doc_id)
        source = meta.get("source", "Tài liệu nội bộ EcoTrack")

        doc_chunks = chunk_text(body)
        for idx, chunk in enumerate(doc_chunks):
            all_chunks.append({
                "id": f"{doc_id}_chunk_{idx}",
                "text": chunk,
                "metadata": {
                    "doc_id": doc_id,
                    "title": str(title),
                    "source": str(source),
                    "chunk_index": idx,
                    "total_chunks": len(doc_chunks),
                }
            })

    return all_chunks


def run_ingest(kb_dir: Path = None, persist_dir: Path = None) -> int:
    """
    Executes idempotent ingestion:
    1. Loads documents from kb_dir.
    2. Chunks and prepares e5 embeddings with 'passage: ' prefix.
    3. Drops and recreates Chroma collection to prevent duplicates.
    4. Persists into ChromaDB.
    Returns total chunk count ingested.
    """
    kb_path = kb_dir or KNOWLEDGE_BASE_DIR
    persist_path = persist_dir or CHROMA_PERSIST_DIR
    persist_path.mkdir(parents=True, exist_ok=True)

    print(f"[Ingest] Starting knowledge base ingestion from {kb_path} ...")
    chunks = load_documents_and_chunk(kb_path)
    if not chunks:
        print("[Ingest] No chunks found to ingest.")
        return 0

    print(f"[Ingest] Generated {len(chunks)} total chunks across documents.")

    # 1. Initialize persistent Chroma client
    client = chromadb.PersistentClient(path=str(persist_path))

    # 2. Recreate collection idempotently (avoid duplicates)
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"[Ingest] Deleted existing collection '{COLLECTION_NAME}' for clean rebuild.")
    except Exception:
        pass  # Collection did not exist yet

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    # 3. Compute Embeddings using multilingual-e5-small (passage prefix)
    print(f"[Ingest] Generating embeddings for {len(chunks)} chunks with {EMBEDDING_MODEL_NAME} on CPU...")
    model = get_embedding_model()
    passage_texts = [f"passage: {c['text']}" for c in chunks]
    embeddings = model.encode(passage_texts, normalize_embeddings=True, show_progress_bar=False).tolist()

    # 4. Insert into ChromaDB collection
    ids = [c["id"] for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]

    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas
    )

    print(f"[Ingest] Successfully indexed {len(chunks)} chunks into ChromaDB at {persist_path}!")
    return len(chunks)


if __name__ == "__main__":
    count = run_ingest()
    print(f"[Done] Knowledge base ingest complete ({count} chunks stored).")
