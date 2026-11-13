from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_create_ideas"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ideas",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(content) BETWEEN 1 AND 2000", name="ck_ideas_content_length"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ideas"),
    )


def downgrade() -> None:
    op.drop_table("ideas")
