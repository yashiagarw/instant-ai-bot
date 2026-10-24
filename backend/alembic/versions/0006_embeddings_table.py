"""One embeddings table for hybrid free-text search (symptoms, synonyms, faults, diagnostic steps).

Moves the existing symptom (fault_items) and customer-phrase vectors into it, with a SHA-256 hash of the text so
later syncs only re-embed changed rows, then drops the old vector columns.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # the model that made the existing vectors
OWNERS = ("symptom", "synonym", "fault", "diagnosis_step")
HASH = "encode(sha256(convert_to({col}, 'UTF8')), 'hex')"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "embeddings",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("owner_type", sa.String(length=14), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("fault_id", sa.BigInteger(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("vector", Vector(dim=384), nullable=False),
        sa.Column("tsv", postgresql.TSVECTOR(), sa.Computed("to_tsvector('simple'::regconfig, text)", persisted=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["fault_id"], ["faults.id"], name=op.f("fk_embeddings_fault_id_faults"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_embeddings")),
        sa.UniqueConstraint(
            "owner_type", "owner_id", "model_name", name=op.f("uq_embeddings_owner_type_owner_id_model_name")
        ),
        sa.CheckConstraint(
            "owner_type IN (" + ", ".join(f"'{o}'" for o in OWNERS) + ")", name=op.f("ck_embeddings_owner_type")
        ),
    )
    op.create_index(op.f("ix_embeddings_fault_id"), "embeddings", ["fault_id"])
    op.create_index(
        "ix_embeddings_vector_hnsw",
        "embeddings",
        ["vector"],
        postgresql_using="hnsw",
        postgresql_ops={"vector": "vector_cosine_ops"},
    )
    op.create_index("ix_embeddings_tsv", "embeddings", ["tsv"], postgresql_using="gin")
    op.create_index(
        "ix_embeddings_text_trgm",
        "embeddings",
        ["text"],
        postgresql_using="gin",
        postgresql_ops={"text": "gin_trgm_ops"},
    )

    # Move the existing vectors (no re-embedding needed: same model, same text).
    op.execute(
        f"""
        INSERT INTO embeddings (owner_type, owner_id, fault_id, model_name, text, text_hash, vector)
        SELECT 'symptom', id, fault_id, '{MODEL}', text, {HASH.format(col="text")}, embedding
        FROM fault_items WHERE type = 'symptom' AND embedding IS NOT NULL
        """
    )
    op.execute(
        f"""
        INSERT INTO embeddings (owner_type, owner_id, fault_id, model_name, text, text_hash, vector)
        SELECT 'synonym', id, fault_id, '{MODEL}', text, {HASH.format(col="text")}, embedding
        FROM customer_phrases WHERE embedding IS NOT NULL AND NOT held_out
        """
    )
    op.drop_index("ix_fault_items_embedding_hnsw", table_name="fault_items")
    op.drop_column("fault_items", "embedding")
    op.drop_index("ix_customer_phrases_embedding_hnsw", table_name="customer_phrases")
    op.drop_column("customer_phrases", "embedding")


def downgrade() -> None:
    op.add_column("customer_phrases", sa.Column("embedding", Vector(dim=384), nullable=True))
    op.create_index(
        "ix_customer_phrases_embedding_hnsw",
        "customer_phrases",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.add_column("fault_items", sa.Column("embedding", Vector(dim=384), nullable=True))
    op.create_index(
        "ix_fault_items_embedding_hnsw",
        "fault_items",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.execute(
        f"""UPDATE fault_items f SET embedding = e.vector FROM embeddings e
        WHERE e.owner_type = 'symptom' AND e.owner_id = f.id AND e.model_name = '{MODEL}'"""
    )
    op.execute(
        f"""UPDATE customer_phrases p SET embedding = e.vector FROM embeddings e
        WHERE e.owner_type = 'synonym' AND e.owner_id = p.id AND e.model_name = '{MODEL}'"""
    )
    op.drop_table("embeddings")
