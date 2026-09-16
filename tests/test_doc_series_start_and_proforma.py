"""INVDS01 Start At floors invoice numbering; the pro-forma series master
supplies the prefix and the user supplies the number.

Uses the dev DB directly; creates throwaway rows and deletes them.
"""
from pathlib import Path

from database import get_db, get_cursor
from modules.FIN01 import model as fin_model
from modules.FIN01 import views as fin_views
from modules.INVDS01 import model as invds

GEN_BILL = Path('modules/FIN01/generate_bill.html').read_text(encoding='utf-8')


# ── INVDS01 Start At ────────────────────────────────────────────────────────

def test_start_at_floors_the_next_invoice_sequence():
    conn = get_db(); cur = get_cursor(conn)
    ids = []
    try:
        ids.append(invds.save_data({'name': 'Test Series', 'prefix': 'ZZTEST', 'start_seq': 500}))
        conn.commit()
        assert fin_model.series_start_seq(cur, 'ZZTEST') == 500
        # Nothing issued yet, so the floor is what the next number becomes.
        assert fin_model.next_invoice_seq(cur, 'ZZTEST', '2026-27') == 500
        # Once numbering passes the floor the natural increment takes over.
        assert fin_model.next_from_seed(700, 500) == 701
    finally:
        for i in ids:
            invds.delete_data(i)
        conn.close()


def test_blank_start_at_means_no_floor():
    conn = get_db(); cur = get_cursor(conn)
    ids = []
    try:
        ids.append(invds.save_data({'name': 'No Floor', 'prefix': 'ZZNONE', 'start_seq': ''}))
        conn.commit()
        assert fin_model.series_start_seq(cur, 'ZZNONE') is None
        assert fin_model.next_invoice_seq(cur, 'ZZNONE', '2026-27') == 1
    finally:
        for i in ids:
            invds.delete_data(i)
        conn.close()


def test_start_at_rejects_junk():
    for bad in ('abc', -5, 0.5):
        try:
            invds._start_seq(bad)
        except ValueError:
            continue
        raise AssertionError(f'{bad!r} should not be accepted as Start At')


def test_proforma_series_master_has_no_start_at():
    """The pro-forma master is name/prefix/default only — a start number there
    would promise a reserved sequence that nothing actually keeps."""
    assert invds.TABLES[invds.PROFORMA_TABLE] is False
    row_id = invds.save_data({'name': 'PF Test', 'prefix': 'ZZPF', 'start_seq': 9},
                             invds.PROFORMA_TABLE)
    try:
        saved = [r for r in invds.get_all(invds.PROFORMA_TABLE) if r['id'] == row_id][0]
        assert 'start_seq' not in saved
        assert saved['prefix'] == 'ZZPF'
    finally:
        invds.delete_data(row_id, invds.PROFORMA_TABLE)


def test_table_name_is_not_free_text():
    """The table goes into an f-string query, so only the two known ones pass."""
    for bad in ('users', 'invoice_doc_series; DROP TABLE users', ''):
        try:
            invds.get_all(bad)
        except ValueError:
            continue
        raise AssertionError(f'{bad!r} should not be accepted as a table')


# ── Pro-forma reference ─────────────────────────────────────────────────────

def test_ref_uses_the_chosen_series_and_typed_number():
    vessel = {'vcn_doc_num': 'VCN-1'}
    fy = fin_views._proforma_fy()
    assert fin_views._proforma_ref(vessel, 'JJLTPL/PI', '0484') == f'JJLTPL/PI/{fy}/0484'
    # A trailing slash on the prefix must not double up.
    assert fin_views._proforma_ref(vessel, 'JJLTPL/PI/', '0484') == f'JJLTPL/PI/{fy}/0484'
    # An old link with no series/number keeps the VCN-derived reference.
    assert fin_views._proforma_ref(vessel, None, None) == f'JJLTPL/PI/{fy}/VCN-1'
    assert fin_views._proforma_ref(vessel, 'ZZPF', None) == f'ZZPF/{fy}/VCN-1'


def test_financial_year_runs_april_to_march():
    from datetime import datetime
    assert fin_views._proforma_fy(datetime(2026, 4, 1)) == '26-27'
    assert fin_views._proforma_fy(datetime(2027, 3, 31)) == '26-27'
    assert fin_views._proforma_fy(datetime(2026, 3, 31)) == '25-26'


# ── Billables screen ────────────────────────────────────────────────────────

def test_proforma_lines_start_unticked():
    """Nothing is pre-selected: the user chooses what the customer is shown."""
    chk = [l for l in GEN_BILL.splitlines() if 'class="pf-chk"' in l]
    assert chk, 'pro forma checkbox not found'
    assert not any('checked' in l for l in chk), chk


def test_number_is_required_before_the_document_opens():
    assert "Enter the pro forma invoice number." in GEN_BILL
    # and the preview is shown from the series the server supplied
    assert 'pfPreview' in GEN_BILL and 'financial_year' in GEN_BILL
