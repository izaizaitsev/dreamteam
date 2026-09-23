"""Editable obligation drafts and in-app director escalation."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade():
    op.alter_column("drafts", "prescription_id", existing_type=sa.String(36), nullable=True)
    op.add_column("drafts", sa.Column("obligation_revision_id", sa.String(36)))
    op.add_column("drafts", sa.Column("template_id", sa.String(30)))
    op.create_index("ix_drafts_obligation_revision_id", "drafts", ["obligation_revision_id"])
    op.create_table("escalations", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("revision_id", sa.String(36), nullable=False),
        sa.Column("director_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "revision_id", name="uq_escalation_org_revision"))
    op.create_index("ix_escalations_organization_id", "escalations", ["organization_id"])
    op.create_index("ix_escalations_revision_id", "escalations", ["revision_id"])

def downgrade():
    op.drop_table("escalations")
    op.drop_index("ix_drafts_obligation_revision_id", table_name="drafts")
    op.drop_column("drafts", "template_id")
    op.drop_column("drafts", "obligation_revision_id")
    op.alter_column("drafts", "prescription_id", existing_type=sa.String(36), nullable=False)
