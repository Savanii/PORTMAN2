"""doc series: a Start At floor on INVDS01, and a pro-forma series master

1. invoice_doc_series.start_seq — the cut-off this series starts numbering
   from. Same job as a cutover_seed row, but per series and editable in
   INVDS01 rather than behind the locked go-live screen; FIN01 floors the next
   invoice sequence at whichever of the two is higher, so neither can quietly
   pull numbering back below the other.

2. proforma_doc_series — name, prefix and default, no start number. Pro-forma
   numbers are typed in by the user at print time (nothing is persisted, so
   there is no sequence to seed). The typed number is appended to the prefix
   verbatim, so the prefix carries its own separator and financial year —
   'JJLTPL/PI-26-27-' + '0484'. Seeded from the prefix FIN01 hard-coded until
   now; finance edits it in INVDS01 each year rather than waiting on a release.

Revision ID: jnpa67_doc_series_start
Revises: jnpa66_service_records_module
Create Date: 2026-09-16
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'jnpa67_doc_series_start'
down_revision: Union[str, None] = 'jnpa66_service_records_module'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE invoice_doc_series ADD COLUMN IF NOT EXISTS start_seq INTEGER')
    op.execute('''
        CREATE TABLE IF NOT EXISTS proforma_doc_series (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            prefix TEXT NOT NULL,
            is_default BOOLEAN DEFAULT FALSE
        )
    ''')
    # The prefix FIN01 used to hard-code, so a fresh install prints the same
    # reference it always did.
    op.execute('''
        INSERT INTO proforma_doc_series (name, prefix, is_default)
        SELECT 'Pro Forma Invoice', 'JJLTPL/PI/', TRUE
        WHERE NOT EXISTS (SELECT 1 FROM proforma_doc_series)
    ''')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS proforma_doc_series')
    op.execute('ALTER TABLE invoice_doc_series DROP COLUMN IF EXISTS start_seq')
