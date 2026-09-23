"""Initial canonical business schema."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("organizations", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(200), nullable=False))
    op.create_table("users", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False), sa.Column("username", sa.String(100), nullable=False, unique=True), sa.Column("role", sa.String(20), nullable=False), sa.Column("password_hash", sa.String(128), nullable=False))
    op.create_index("ix_users_organization_id", "users", ["organization_id"])
    op.create_table("regulatory_documents", sa.Column("id", sa.String(36), primary_key=True), sa.Column("title", sa.String(300), nullable=False), sa.Column("source_url", sa.String(1000)))
    op.create_table("regulatory_revisions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("document_id", sa.String(36), sa.ForeignKey("regulatory_documents.id"), nullable=False), sa.Column("section", sa.String(200), nullable=False), sa.Column("effective_from", sa.Date(), nullable=False), sa.Column("effective_to", sa.Date()), sa.Column("content", sa.Text(), nullable=False), sa.Column("checksum", sa.String(64), nullable=False))
    op.create_index("ix_regulatory_revisions_document_id", "regulatory_revisions", ["document_id"])
    op.create_table("consultations", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False), sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("question", sa.Text(), nullable=False), sa.Column("target_date", sa.Date(), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("answer", sa.Text()), sa.Column("citations", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_consultations_organization_id", "consultations", ["organization_id"])
    op.create_table("ai_generations", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False), sa.Column("resource", sa.String(50), nullable=False), sa.Column("resource_id", sa.String(36), nullable=False), sa.Column("provider", sa.String(40), nullable=False), sa.Column("model", sa.String(100), nullable=False), sa.Column("prompt_version", sa.String(30), nullable=False), sa.Column("target_date", sa.Date()), sa.Column("source_ids", sa.JSON(), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_ai_generations_organization_id", "ai_generations", ["organization_id"])
    op.create_table("prescriptions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False), sa.Column("title", sa.String(300), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_prescriptions_organization_id", "prescriptions", ["organization_id"])
    op.create_table("drafts", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False), sa.Column("prescription_id", sa.String(36), sa.ForeignKey("prescriptions.id"), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("citations", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_drafts_organization_id", "drafts", ["organization_id"])
    op.create_index("ix_drafts_prescription_id", "drafts", ["prescription_id"])
    op.create_table("obligations", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False), sa.Column("title", sa.String(300), nullable=False), sa.Column("description", sa.Text(), nullable=False), sa.Column("due_date", sa.Date(), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("priority", sa.String(20), nullable=False), sa.Column("responsible_id", sa.String(36), sa.ForeignKey("users.id")), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_obligations_organization_id", "obligations", ["organization_id"])
    op.create_table("background_jobs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False), sa.Column("kind", sa.String(40), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("result", sa.JSON()), sa.Column("error", sa.String(500)))
    op.create_index("ix_background_jobs_organization_id", "background_jobs", ["organization_id"])
    op.create_table("audit_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False), sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("resource", sa.String(50), nullable=False), sa.Column("resource_id", sa.String(36), nullable=False), sa.Column("action", sa.String(50), nullable=False), sa.Column("at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_audit_events_organization_id", "audit_events", ["organization_id"])

def downgrade():
    for table in ("audit_events", "background_jobs", "obligations", "drafts", "prescriptions", "ai_generations", "consultations", "regulatory_revisions", "regulatory_documents", "users", "organizations"):
        op.drop_table(table)
