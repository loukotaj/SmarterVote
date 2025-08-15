"""Configuration defaults for the corpus step."""

import os

DEFAULT_CONFIG = {
    "chunk_size": int(os.getenv("CHROMA_CHUNK_SIZE", "500")),
    "chunk_overlap": int(os.getenv("CHROMA_CHUNK_OVERLAP", "50")),
    "embedding_model": os.getenv("CHROMA_EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
    "similarity_threshold": float(os.getenv("CHROMA_SIMILARITY_THRESHOLD", "0.7")),
    "max_results": int(os.getenv("CHROMA_MAX_RESULTS", "100")),
    "persist_directory": os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db"),
}
