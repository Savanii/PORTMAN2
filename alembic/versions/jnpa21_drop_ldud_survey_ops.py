"""jnpa phase1 - drop LDUD ops_commenced + draft-survey datetime columns

Removed from the LDUD grid and now dropped from the schema. Kept on purpose:
  - initial_draft_survey_quantity : still read by RP01 barge_report (live)
  - material_po_number            : still read by FIN01 billing (live)
These two are UI-hidden but retained until their consumers are reworked.

Revision ID: jnpa21_drop_ldud_survey_ops
Revises: jnpa20_parcel_ops_qty_term
Create Date: 2026-06-19
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa21_drop_ldud_survey_ops'
down_revision: Union[str, None] = 'jnpa20_parcel_ops_qty_term'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        ALTER TABLE ldud_header DROP COLUMN IF EXISTS ops_commenced;
        ALTER TABLE ldud_header DROP COLUMN IF EXISTS initial_draft_survey_from;
        ALTER TABLE ldud_header DROP COLUMN IF EXISTS initial_draft_survey_to;
        ALTER TABLE ldud_header DROP COLUMN IF EXISTS final_draft_survey_from;
        ALTER TABLE ldud_header DROP COLUMN IF EXISTS final_draft_survey_to;
    ''')


def downgrade() -> None:
    op.execute('''
        ALTER TABLE ldud_header ADD COLUMN IF NOT EXISTS ops_commenced TEXT;
        ALTER TABLE ldud_header ADD COLUMN IF NOT EXISTS initial_draft_survey_from TEXT;
        ALTER TABLE ldud_header ADD COLUMN IF NOT EXISTS initial_draft_survey_to TEXT;
        ALTER TABLE ldud_header ADD COLUMN IF NOT EXISTS final_draft_survey_from TEXT;
        ALTER TABLE ldud_header ADD COLUMN IF NOT EXISTS final_draft_survey_to TEXT;
    ''')
