"""pgvector-backed runbook retrieval client.

Falls back gracefully when PostgreSQL + pgvector are unavailable.
Callers receive [] and must fall back to keyword search.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

_EMBED_MODEL = "all-MiniLM-L6-v2"
_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS runbook_vectors (
    key TEXT PRIMARY KEY,
    title TEXT,
    metadata_json TEXT,
    embedding vector(384)
)
"""


class VectorStoreClient:
    def __init__(self) -> None:
        self._available = False
        self._model = None
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(_EMBED_MODEL)
            from src.db import engine
            from sqlalchemy import text
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.execute(text(_TABLE_DDL))
                conn.commit()
            self._engine = engine
            self._available = True
            logger.info("VectorStoreClient: pgvector ready")
        except Exception as exc:
            logger.warning("VectorStoreClient: unavailable (%s) — keyword fallback active", exc)

    def _embed(self, text: str) -> list:
        return self._model.encode(text).tolist()

    def index_runbook(self, key: str, text: str, metadata: dict) -> None:
        if not self._available:
            return
        import json
        from sqlalchemy import text as sql_text
        vec = self._embed(text)
        with self._engine.begin() as conn:
            conn.execute(
                sql_text(
                    "INSERT INTO runbook_vectors (key, title, metadata_json, embedding) "
                    "VALUES (:key, :title, :meta, :emb) "
                    "ON CONFLICT (key) DO UPDATE SET embedding=EXCLUDED.embedding, "
                    "metadata_json=EXCLUDED.metadata_json"
                ),
                {"key": key, "title": metadata.get("title", key),
                 "meta": json.dumps(metadata), "emb": str(vec)},
            )

    def search(self, query: str, top_k: int = 3) -> list:
        if not self._available:
            return []
        try:
            import json
            from sqlalchemy import text as sql_text
            vec = self._embed(query)
            with self._engine.connect() as conn:
                rows = conn.execute(
                    sql_text(
                        "SELECT key, title, metadata_json, "
                        "1 - (embedding <=> :emb) AS score "
                        "FROM runbook_vectors "
                        "ORDER BY embedding <=> :emb LIMIT :k"
                    ),
                    {"emb": str(vec), "k": top_k},
                ).fetchall()
            results = []
            for row in rows:
                meta = json.loads(row.metadata_json)
                meta["score"] = round(float(row.score), 4)
                results.append(meta)
            return results
        except Exception as exc:
            logger.warning("VectorStoreClient.search failed: %s", exc)
            return []
