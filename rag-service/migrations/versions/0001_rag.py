"""Independent RAG metadata, revisions, passages and jobs."""
from alembic import op
import sqlalchemy as sa

revision = "0001_rag"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("rag_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_rag_documents_org_category", "rag_documents", ["organization_id", "category"])
    op.create_table("rag_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("rag_documents.id"), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(255), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_to", sa.Date()),
        sa.Column("due_date", sa.Date()),
        sa.Column("date_provenance", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "category", "checksum", name="uq_rag_upload_checksum"))
    op.create_index("ix_rag_revisions_document_id", "rag_revisions", ["document_id"])
    op.create_table("rag_passages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("rag_revisions.id"), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(300), nullable=False),
        sa.Column("fragment", sa.Text(), nullable=False))
    op.create_index("ix_rag_passages_revision_id", "rag_passages", ["revision_id"])
    op.execute("CREATE INDEX ix_rag_passages_fts ON rag_passages USING GIN (to_tsvector('russian', fragment))")
    op.create_table("rag_ingestion_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("rag_revisions.id"), nullable=False),
        sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error_code", sa.String(50)),
        sa.Column("error_message", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_rag_ingestion_jobs_org", "rag_ingestion_jobs", ["organization_id"])

def downgrade():
    op.drop_table("rag_ingestion_jobs")
    op.drop_table("rag_passages")
    op.drop_table("rag_revisions")
    op.drop_table("rag_documents")

