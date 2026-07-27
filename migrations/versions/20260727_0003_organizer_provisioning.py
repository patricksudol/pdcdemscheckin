"""Add organizer provisioning and session invalidation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_0003"
down_revision: str | Sequence[str] | None = "20260727_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizers",
        sa.Column("session_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_table(
        "password_setup_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizer_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["organizers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organizer_id"], ["organizers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_password_setup_tokens_organizer_id",
        "password_setup_tokens",
        ["organizer_id"],
    )
    op.create_index(
        "ix_password_setup_tokens_token_hash",
        "password_setup_tokens",
        ["token_hash"],
    )
    op.create_index(
        "ix_password_setup_tokens_expires_at",
        "password_setup_tokens",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_table("password_setup_tokens")
    op.drop_column("organizers", "session_version")
