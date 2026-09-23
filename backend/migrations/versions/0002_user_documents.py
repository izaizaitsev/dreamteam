"""Store organization-private extracted documents separately from regulatory sources."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("ai_generations", sa.Column("user_document_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.create_table("user_documents", sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
                    sa.Column("prescription_id", sa.String(36), sa.ForeignKey("prescriptions.id"), nullable=False),
                    sa.Column("filename", sa.String(255), nullable=False),
                    sa.Column("mime_type", sa.String(100), nullable=False),
                    sa.Column("checksum", sa.String(64), nullable=False),
                    sa.Column("extracted_text", sa.Text(), nullable=False),
                    sa.Column("status", sa.String(20), nullable=False),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_user_documents_organization_id", "user_documents", ["organization_id"])
    op.create_index("ix_user_documents_prescription_id", "user_documents", ["prescription_id"])

def downgrade():
    op.drop_table("user_documents")
    op.drop_column("ai_generations", "user_document_ids")
