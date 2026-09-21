"""INVDS01: remember how wide the Start At was typed, so 0418 stays 0418

Start At is stored as an integer, so "0418" became 418 and the invoice went
out as PREFIX/418 instead of PREFIX/0418. The number is right; the width is
what was lost, and an integer column cannot carry it.

seq_width records the number of digits the operator typed. The sequence itself
stays an integer -- doc_series_seq is still 418, ordering and the seed floor
are unchanged -- and only the printed invoice_number is zero-padded to this
width. NULL means "no padding", which is what every existing series gets, so
nothing already issued changes shape.

Backfills from the stored start_seq: a series seeded at 418 keeps 3, one
seeded at 0418 cannot be recovered (the zero is already gone) and the operator
re-enters it.

Revision ID: jnpa72_invoice_series_seq_width
Revises: jnpa71_finance_real_to_numeric
Create Date: 2026-09-21
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa72_invoice_series_seq_width'
down_revision: Union[str, None] = 'jnpa71_finance_real_to_numeric'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE invoice_doc_series ADD COLUMN IF NOT EXISTS seq_width SMALLINT')
    # Existing series: the width they already number at. Leading zeros that
    # were typed before this column existed are unrecoverable.
    op.execute('''
        UPDATE invoice_doc_series
           SET seq_width = LENGTH(start_seq::text)
         WHERE start_seq IS NOT NULL AND seq_width IS NULL
    ''')


def downgrade() -> None:
    op.execute('ALTER TABLE invoice_doc_series DROP COLUMN IF EXISTS seq_width')
