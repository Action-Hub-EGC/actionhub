"""deduplicate dataset view and download records in the database

Revision ID: 005
Revises: 004
Create Date: 2026-11-22 18:00:00.000000

Decision #66: a dataset download (and view) counts once per user or anonymous
visitor, dataset and browser cookie. The services checked for an existing row
before inserting, but nothing stopped two concurrent requests from both
inserting it. A unique index closes that gap. ``user_id`` is NULL for anonymous
visitors and MariaDB never treats two NULLs as equal in a unique index, so the
index uses a stored generated column, ``user_key = COALESCE(user_id, 0)``.

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

USER_KEY = "COALESCE(user_id, 0)"

# (table, cookie column, unique constraint name)
RECORD_TABLES = (
    ("ds_download_record", "download_cookie", "uq_ds_download_record_once"),
    ("ds_view_record", "view_cookie", "uq_ds_view_record_once"),
)


def upgrade():
    for table, cookie, constraint in RECORD_TABLES:
        # Duplicates that slipped in before the index would make it fail.
        # Keep the oldest row of each group, which holds the first date.
        op.execute(f"""
            DELETE newer FROM {table} AS newer
            JOIN {table} AS older
              ON COALESCE(newer.user_id, 0) = COALESCE(older.user_id, 0)
             AND newer.dataset_id = older.dataset_id
             AND newer.{cookie} = older.{cookie}
             AND newer.id > older.id
            """)
        op.add_column(
            table,
            sa.Column("user_key", sa.Integer(), sa.Computed(USER_KEY, persisted=True)),
        )
        op.create_unique_constraint(constraint, table, ["user_key", "dataset_id", cookie])


def downgrade():
    for table, _cookie, constraint in RECORD_TABLES:
        op.drop_constraint(constraint, table, type_="unique")
        op.drop_column(table, "user_key")
