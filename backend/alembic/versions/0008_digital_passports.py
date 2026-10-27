"""Opt-in public passports, separate guardian consents and protocol proofs."""

from alembic import op
import sqlalchemy as sa

revision = "0008_passports"
down_revision = "0007_teams"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "passport_publications",
        sa.Column(
            "athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), primary_key=True
        ),
        sa.Column("slug", sa.String(64), unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "show_results", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "show_rating", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("show_team", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "show_rusada", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("consent_at", sa.DateTime(timezone=True)),
        sa.Column("consent_version", sa.String(30)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "passport_guardian_consents",
        sa.Column(
            "athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), primary_key=True
        ),
        sa.Column("guardian_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("document", sa.LargeBinary(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.CheckConstraint("status IN ('pending','approved','rejected')"),
    )
    op.create_table(
        "public_protocol_proofs",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column(
            "athlete_id", sa.Integer(), sa.ForeignKey("athletes.id"), nullable=False
        ),
        sa.Column(
            "protocol_version_id",
            sa.Integer(),
            sa.ForeignKey("protocol_versions.id"),
            nullable=False,
        ),
        sa.Column("publication_slug", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("publication_slug", "protocol_version_id"),
    )


def downgrade():
    op.drop_table("public_protocol_proofs")
    op.drop_table("passport_guardian_consents")
    op.drop_table("passport_publications")
