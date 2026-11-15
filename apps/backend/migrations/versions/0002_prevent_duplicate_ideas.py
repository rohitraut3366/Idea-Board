from collections.abc import Sequence

from alembic import op

revision: str = "0002_prevent_duplicate_ideas"
down_revision: str | Sequence[str] | None = "0001_create_ideas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A hash exclusion constraint compares full text without a B-tree key-size limit.
    op.create_exclude_constraint("ex_ideas_content", "ideas", ("content", "="), using="hash")


def downgrade() -> None:
    op.drop_constraint("ex_ideas_content", "ideas")
