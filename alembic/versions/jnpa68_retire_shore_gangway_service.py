"""retire SHGW01 (Shore Gangway Charges) as a system service

Shore Gangway is being rebuilt as an ordinary configurable service in FSTM01
and billed through SRV02, so the seeded system row has to go. jnpa37 still
seeds it (applied migrations are not rewritten); on a fresh database this
removes it again a few revisions later, which costs one wasted insert and
keeps the history honest.

Removal is conditional, because prod may already have documents on it:

  * nothing references the row  -> DELETE it outright
  * something does              -> leave the row for those documents but take
                                   it out of circulation (is_system=0 so it is
                                   no longer admin-locked, is_active=0 and
                                   is_billable=0 so it stops being offered)

Either way it disappears from the service pickers and from FIN01; a bill or
service record that already used it keeps working.

Revision ID: jnpa68_retire_shore_gangway
Revises: jnpa67_doc_series_start
Create Date: 2026-09-18
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'jnpa68_retire_shore_gangway'
down_revision: Union[str, None] = 'jnpa67_doc_series_start'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CODE = 'SHGW01'


def upgrade() -> None:
    op.execute(f"""
        DO $$
        DECLARE
            svc_id INTEGER;
            refs   INTEGER;
        BEGIN
            SELECT id INTO svc_id FROM finance_service_types WHERE service_code = '{CODE}';
            IF svc_id IS NULL THEN
                RETURN;
            END IF;

            SELECT (SELECT COUNT(*) FROM bill_lines               WHERE service_type_id = svc_id)
                 + (SELECT COUNT(*) FROM service_records          WHERE service_type_id = svc_id)
                 + (SELECT COUNT(*) FROM customer_agreement_lines WHERE service_type_id = svc_id)
                 + (SELECT COUNT(*) FROM parcel_charge_billed     WHERE service_type_id = svc_id)
                 + (SELECT COUNT(*) FROM service_field_definitions WHERE service_type_id = svc_id)
              INTO refs;

            IF refs = 0 THEN
                DELETE FROM finance_service_types WHERE id = svc_id;
                RAISE NOTICE 'SHGW01 deleted (unreferenced)';
            ELSE
                UPDATE finance_service_types
                   SET is_system = 0, is_active = 0, is_billable = 0
                 WHERE id = svc_id;
                RAISE NOTICE 'SHGW01 kept for % existing reference(s), deactivated', refs;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Puts the system row back as jnpa37 seeded it. Deliberately does not
    # restore rates or agreements — those were never deleted.
    op.execute(f"""
        INSERT INTO finance_service_types
            (service_code, service_name, service_category, gl_code, sap_gl_account,
             uom, sac_code, is_system, is_active, is_billable, created_by, created_date)
        SELECT '{CODE}', 'Shore Gangway Charges', 'Other', '4101076100', '4101076100',
               'OTH', '996719', 1, 1, 1, 'system', CURRENT_DATE::text
        WHERE NOT EXISTS (SELECT 1 FROM finance_service_types WHERE service_code = '{CODE}');
        UPDATE finance_service_types
           SET is_system = 1, is_active = 1, is_billable = 1
         WHERE service_code = '{CODE}';
    """)
