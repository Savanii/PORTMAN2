"""service_records.module_code — tells SRV01 rows from SRV02 rows

SRV02 is the same service recording screen as SRV01 with a different record
number format (SRV1, SRV2, … instead of a plain 7001, 7002, …). Both write to
service_records, so FIN01 bills them identically and needs no change; this
column is only so each module lists its own records and continues its own
numbering.

Existing rows default to SRV01, which is what they are.

Revision ID: jnpa66_service_records_module
Revises: jnpa65_mail_attachments_gst
Create Date: 2026-09-16
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'jnpa66_service_records_module'
down_revision: Union[str, None] = 'jnpa65_mail_attachments_gst'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE service_records
        ADD COLUMN IF NOT EXISTS module_code TEXT NOT NULL DEFAULT 'SRV01'
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_service_records_module
        ON service_records (module_code)
    """)
    # SRV02 is the same screen as SRV01, so whoever may work SRV01 may work
    # SRV02. Users with no SRV01 row get nothing here either — the admin grants
    # it in ADMIN > Permissions like any other module.
    op.execute("""
        INSERT INTO module_permissions (user_id, module_code, can_read, can_add, can_edit, can_delete)
        SELECT user_id, 'SRV02', can_read, can_add, can_edit, can_delete
        FROM module_permissions WHERE module_code = 'SRV01'
        ON CONFLICT (user_id, module_code) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM module_permissions WHERE module_code = 'SRV02'")
    op.execute('DROP INDEX IF EXISTS idx_service_records_module')
    op.execute('ALTER TABLE service_records DROP COLUMN IF EXISTS module_code')
