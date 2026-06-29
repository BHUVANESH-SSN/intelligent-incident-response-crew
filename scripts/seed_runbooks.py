#!/usr/bin/env python
"""Embed and upsert the built-in runbooks into pgvector.

Run after starting PostgreSQL with pgvector:
    DATABASE_URL=postgresql://user:pw@localhost/incidents python scripts/seed_runbooks.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import init_db
from src.integrations.vector_store import VectorStoreClient
from src.tools import RUNBOOKS


def main():
    init_db()
    client = VectorStoreClient()
    if not client._available:
        print("pgvector not available — skipping. Set DATABASE_URL to a PostgreSQL URL.")
        return
    for key, runbook in RUNBOOKS.items():
        text = " ".join([
            runbook.get("title", ""),
            " ".join(runbook.get("keywords", [])),
            " ".join(runbook.get("steps", [])),
        ])
        client.index_runbook(key, text, runbook)
    print(f"Seeded {len(RUNBOOKS)} runbooks.")


if __name__ == "__main__":
    main()
