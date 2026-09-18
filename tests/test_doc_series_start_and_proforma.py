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

def test_ref_is_the_prefix_with_the_number_appended():
    """No separator and no year are inserted — the series prefix owns the whole
    shape of the reference, so finance can change it without a code change."""
    # The fallback is whatever identifies the document — the VCN doc number for
    # a cargo pro-forma, the record number for a services one.
    fb = 'VCN-1'
    assert fin_views._proforma_ref(fb, 'JJLTPL/PI-26-27-', '0484') == 'JJLTPL/PI-26-27-0484'
    assert fin_views._proforma_ref(fb, 'JJLTPL/PI/', '0484') == 'JJLTPL/PI/0484'
    # Surrounding whitespace on the stored prefix must not reach the document.
    assert fin_views._proforma_ref(fb, '  ZZPF/  ', ' 7 ') == 'ZZPF/7'
    # An old link with no series/number keeps the fallback-derived reference.
    assert fin_views._proforma_ref(fb, None, None) == 'JJLTPL/PI/VCN-1'
    assert fin_views._proforma_ref(fb, 'ZZPF-', None) == 'ZZPF-VCN-1'


def test_nothing_adds_a_financial_year():
    """The year lives in the prefix now; a stray FY here would double it up."""
    assert not hasattr(fin_views, '_proforma_fy')
    assert 'financial_year' not in GEN_BILL


# ── Billables screen ────────────────────────────────────────────────────────

def test_billable_lines_start_unticked():
    """Nothing is pre-selected on either stage — the user picks the lines that
    go on the bill or in front of the customer, rather than unticking a screen
    that arrived fully ticked."""
    for cls in ('pf-chk', 'bl-chk'):
        chk = [l for l in GEN_BILL.splitlines() if f'class="{cls}"' in l]
        assert chk, f'{cls} checkbox not found'
        assert not any('checked' in l for l in chk), chk


def test_number_is_required_before_the_document_opens():
    assert "Enter the pro forma invoice number." in GEN_BILL
    # and the preview is shown from the prefix the server supplied
    assert 'pfPreview' in GEN_BILL and 'proforma-series' in GEN_BILL
