"""add audit timestamp columns

Revision ID: 73cfdb5307bb
Revises: 2c39994ff739
Create Date: 2026-09-08 20:03:06.575211

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "73cfdb5307bb"
down_revision: Union[str, Sequence[str], None] = "2c39994ff739"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "account",
    "budget",
    "categorization_rule",
    "category",
    "csv_profile",
    "recurring_pattern",
    "transaction",
)


def upgrade() -> None:
    # SQLite rejects `ADD COLUMN ... DEFAULT CURRENT_TIMESTAMP NOT NULL` on a
    # populated table ("non-constant default"), so recreate each table via
    # batch mode — the CREATE TABLE default is allowed and backfills existing
    # rows to now().
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column(
                    "created_at",
                    sa.DateTime(),
                    server_default=sa.text("(CURRENT_TIMESTAMP)"),
                    nullable=False,
                )
            )
            batch.add_column(
                sa.Column(
                    "updated_at",
                    sa.DateTime(),
                    server_default=sa.text("(CURRENT_TIMESTAMP)"),
                    nullable=False,
                )
            )


def downgrade() -> None:
    for table in reversed(_TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("updated_at")
            batch.drop_column("created_at")
