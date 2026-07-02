"""jnpa phase1 - seed system finance service types (with SAP/GST accounting)

Seeds only the SYSTEM (admin-locked) services from the Service & Accounting
Codes sheet — #1,2,3,4,10: Cargo Handling, Infrastructure & Misc, MLA,
Shore Gangway, Toll. Cargo Handling (#1) is split into CHGU01 (Unloading /
Import) and CHGL01 (Loading / Export). The remaining sheet rows (#5-9:
commission, compressor, fresh water, nitrogen, other misc) are ordinary
services users add themselves in FSTM01, so they are NOT seeded here.

Idempotent: inserts each row if its service_code is missing, then updates the
accounting fields — safe to re-run. Existing demo rows (EQP001/DEL001/…) are
left untouched.

Revision ID: jnpa37_seed_finance_services
Revises: jnpa36_lueu_shortclose
Create Date: 2026-07-01
"""
from datetime import date
from typing import Sequence, Union
from alembic import op
from sqlalchemy import text

revision: str = 'jnpa37_seed_finance_services'
down_revision: Union[str, None] = 'jnpa36_lueu_shortclose'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GST_18 = 4   # gst_rates.id for 'GST 18%'
GST_0 = 1    # gst_rates.id for 'GST 0%'

# common accounting for the revenue services (CSV rows 1-9)
_C = dict(
    sac_code='996719', gst_rate_id=GST_18, service_sale_flag='A',
    sap_profit_center='5250500000', sap_cost_center=None, sap_tax_code=None,
    sap_igst_gl='1404051142', sap_cgst_gl='1404051140', sap_sgst_gl='1404051141',
    sap_tds_gl='2105610093', sap_tcs_gl=None,
    is_tds=1, tds_percent=2, is_tcs=0, tcs_percent=None, is_triplicate=0,
    is_billable=1, is_active=1, is_system=0,
)


def _row(**kw):
    r = dict(_C)
    r.update(kw)
    return r


SERVICES = [
    _row(service_code='CHGU01', service_name='Cargo Handling Unloading', service_category='Cargo',
         gl_code='4101076030', sap_gl_account='4101076030', uom='MTS', is_system=1),
    _row(service_code='CHGL01', service_name='Cargo Handling Loading', service_category='Cargo',
         gl_code='4101076030', sap_gl_account='4101076030', uom='MTS', is_system=1),
    _row(service_code='INFM01', service_name='Infrastructure and Miscellaneous Charges', service_category='Cargo',
         gl_code='4101076010', sap_gl_account='4101076010', uom='MTS', is_system=1),
    _row(service_code='MLAC01', service_name='MLA Charges', service_category='MLA',
         gl_code='4101076010', sap_gl_account='4101076030', uom='MTS', is_system=1),
    _row(service_code='SHGW01', service_name='Shore Gangway Charges', service_category='Other',
         gl_code='4101076100', sap_gl_account='4101076100', uom='OTH', is_system=1),
    # Toll (#10): billed per tonne. Pass-through collection so GST 0% and no GST GLs.
    _row(service_code='TOLL01', service_name='Toll Charges', service_category='Toll',
         gl_code=None, sap_gl_account=None, uom='MTS', is_system=1,
         gst_rate_id=GST_0, is_billable=1, is_tds=0, tds_percent=0,
         sap_igst_gl=None, sap_cgst_gl=None, sap_sgst_gl=None, sap_tds_gl=None),
]

_NEW_CODES = ['INFM01', 'MLAC01', 'SHGW01', 'TOLL01']

_UPDATE_FIELDS = ['service_name', 'service_category', 'gl_code', 'sac_code', 'gst_rate_id', 'uom',
                  'is_billable', 'is_active', 'is_system', 'sap_gl_account', 'sap_tax_code',
                  'sap_profit_center', 'sap_cost_center', 'sap_igst_gl', 'sap_cgst_gl', 'sap_sgst_gl',
                  'service_sale_flag', 'sap_tds_gl', 'sap_tcs_gl', 'is_tds', 'tds_percent',
                  'is_tcs', 'tcs_percent', 'is_triplicate']


def upgrade() -> None:
    conn = op.get_bind()
    today = date.today().isoformat()
    for s in SERVICES:
        params = dict(s, today=today)
        conn.execute(text(
            "INSERT INTO finance_service_types (service_code, service_name, created_by, created_date) "
            "SELECT :service_code, :service_name, 'system', :today "
            "WHERE NOT EXISTS (SELECT 1 FROM finance_service_types WHERE service_code = :service_code)"
        ), params)
        set_clause = ', '.join(f'{f} = :{f}' for f in _UPDATE_FIELDS)
        conn.execute(text(
            f"UPDATE finance_service_types SET {set_clause} WHERE service_code = :service_code"
        ), params)


def downgrade() -> None:
    # Remove only the rows this migration introduced; CHGU01/CHGL01 pre-existed
    # and their prior values can't be restored, so they are left as-is.
    conn = op.get_bind()
    conn.execute(text(
        "DELETE FROM finance_service_types WHERE service_code = ANY(:codes)"
    ), {'codes': _NEW_CODES})
