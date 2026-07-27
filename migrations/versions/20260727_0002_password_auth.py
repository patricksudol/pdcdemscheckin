"""Add organizer password authentication."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_0002"
down_revision: str | Sequence[str] | None = "20260727_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organizers", sa.Column("password_hash", sa.String(255), nullable=True))
    op.drop_constraint("organizers_google_subject_key", "organizers", type_="unique")
    op.drop_column("organizers", "google_subject")


def downgrade() -> None:
    op.add_column(
        "organizers", sa.Column("google_subject", sa.String(255), nullable=True)
    )
    op.execute("UPDATE organizers SET google_subject = 'legacy-' || CAST(id AS VARCHAR)")
    op.alter_column("organizers", "google_subject", existing_type=sa.String(255), nullable=False)
    op.create_unique_constraint(
        "organizers_google_subject_key", "organizers", ["google_subject"]
    )
    op.drop_column("organizers", "password_hash")
