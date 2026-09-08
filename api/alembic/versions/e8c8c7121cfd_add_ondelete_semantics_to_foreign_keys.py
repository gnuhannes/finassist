"""add ondelete semantics to foreign keys

Revision ID: e8c8c7121cfd
Revises: 73cfdb5307bb
Create Date: 2026-09-08 21:29:02.073516

Follow-up to #96 (PRAGMA foreign_keys=ON). All FKs were created without an
``ON DELETE`` clause (i.e. RESTRICT). This gives each one an explicit policy:

* RESTRICT — deleting the parent is blocked while children exist
* SET NULL — the child's FK column is nulled (only nullable columns)
* CASCADE  — the child row is deleted with the parent

SQLite can't ``ALTER`` a constraint, so every table is recreated via batch
mode. A naming convention lets the pre-existing unnamed FKs be addressed by
``drop_constraint``.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8c8c7121cfd"
down_revision: Union[str, Sequence[str], None] = "73cfdb5307bb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NAMING = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}

# table -> [(column, referred_table, ondelete policy)]
_FKS: dict[str, list[tuple[str, str, str]]] = {
    "budget": [("category_id", "category", "CASCADE")],
    "categorization_rule": [("category_id", "category", "CASCADE")],
    "category": [("parent_id", "category", "SET NULL")],
    "recurring_pattern": [
        ("account_id", "account", "CASCADE"),
        ("category_id", "category", "SET NULL"),
    ],
    "transaction": [
        ("account_id", "account", "RESTRICT"),
        ("category_id", "category", "SET NULL"),
    ],
    "transfer_candidate": [
        ("from_transaction_id", "transaction", "CASCADE"),
        ("to_transaction_id", "transaction", "CASCADE"),
    ],
    "watch_folder_config": [
        ("account_id", "account", "CASCADE"),
        ("profile_id", "csv_profile", "SET NULL"),
    ],
}


def _rebuild(*, with_ondelete: bool) -> None:
    for table, fks in _FKS.items():
        with op.batch_alter_table(table, naming_convention=_NAMING) as batch_op:
            for column, referred, _policy in fks:
                batch_op.drop_constraint(
                    f"fk_{table}_{column}_{referred}", type_="foreignkey"
                )
            for column, referred, policy in fks:
                batch_op.create_foreign_key(
                    f"fk_{table}_{column}_{referred}",
                    referred,
                    [column],
                    ["id"],
                    ondelete=policy if with_ondelete else None,
                )


def upgrade() -> None:
    _rebuild(with_ondelete=True)


def downgrade() -> None:
    _rebuild(with_ondelete=False)
