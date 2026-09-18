"""The pro-forma names the payer, then the VCN consignee(s) as 'A/C <name>'.

VCN01's parcel sub-table has both: 'Payment will be made by' (importer_name)
is who the bill goes to, 'Consignee' (consigner_name) is who it is on account
of. Dev DB with a throwaway VCN + parcels, cleaned up.
"""
import re
import zlib

from database import get_db, get_cursor
from modules.FIN01 import proforma_pdf, views

PAYER = 'ZZPAYER CO'
C1, C2 = 'ZZ CONSIGNEE ONE', 'ZZ CONSIGNEE TWO'


def _setup(cur):
    cur.execute("INSERT INTO vcn_header (operation_type, vcn_doc_num, vessel_name) "
                "VALUES ('Import','VCN-AC-1','ACVESSEL') RETURNING id")
    vid = cur.fetchone()['id']
    ids = []
    for seq, (parcel, consignee) in enumerate([('P1', C1), ('P2', C2)], start=1):
        cur.execute("""INSERT INTO vcn_consigners
            (vcn_id, parcel_no, cargo_name, quantity, consigner_name, importer_name,
             pipeline_name, unload_terminal, toll_applicable, equipment_names, parcel_seq)
            VALUES (%s,%s,'OIL','100',%s,%s,'PL1','T1',FALSE,'',%s) RETURNING id""",
            [vid, parcel, consignee, PAYER, seq])
        ids.append(cur.fetchone()['id'])
    return vid, ids


def _teardown(vid):
    conn = get_db(); cur = get_cursor(conn)
    cur.execute('DELETE FROM vcn_header WHERE id=%s', [vid])   # cascades consigners
    conn.commit(); conn.close()


def _lines(pid1, pid2=None):
    out = [{'cargo_source_type': 'VCN_IMPORT', 'cargo_source_id': pid1}]
    if pid2:
        out.append({'cargo_source_type': 'VCN_IMPORT', 'cargo_source_id': pid2})
    return out


def test_consignees_follow_the_parcels_on_the_document():
    conn = get_db(); cur = get_cursor(conn)
    vid, (p1, p2) = _setup(cur)
    conn.commit()
    try:
        assert views._parcel_consignees(cur, _lines(p1, p2)) == [C1, C2]
        # unticking a parcel drops its consignee from the document too
        assert views._parcel_consignees(cur, _lines(p2)) == [C2]
        # several charges on one parcel must not repeat its consignee
        assert views._parcel_consignees(cur, _lines(p1) * 4) == [C1]
        # a line with no parcel (nothing to consign) contributes nothing
        assert views._parcel_consignees(cur, [{'cargo_source_type': 'VCN_IMPORT',
                                               'cargo_source_id': None}]) == []
    finally:
        conn.close()
        _teardown(vid)


def test_consignee_order_follows_the_lines_not_the_ids():
    conn = get_db(); cur = get_cursor(conn)
    vid, (p1, p2) = _setup(cur)
    conn.commit()
    try:
        assert views._parcel_consignees(cur, _lines(p2, p1)) == [C2, C1]
    finally:
        conn.close()
        _teardown(vid)


def _drawn_text(pdf_bytes):
    raw = ''
    for m in re.finditer(rb'stream\r?\n(.*?)\r?\nendstream', pdf_bytes, re.S):
        try:
            raw += zlib.decompress(m.group(1)).decode('latin-1')
        except Exception:
            pass
    return re.findall(r'\((.*?)\)\s*Tj', raw)


def test_ac_lines_print_under_the_payer():
    ctx = dict(_MIN_CTX, customer={'name': PAYER, 'gstin': '27AAAAA0000A1Z5'},
               ac_names=[C1, C2])
    drawn = _drawn_text(proforma_pdf.render(ctx))
    i = drawn.index(PAYER)
    assert drawn[i + 1] == f'A/C {C1}'
    assert drawn[i + 2] == f'A/C {C2}'
    assert drawn[i + 3].startswith('GSTIN:-')


def test_no_consignee_means_no_ac_line():
    """A parcel with the Consignee column left blank must not print 'A/C '."""
    for names in ([], ['', None]):
        ctx = dict(_MIN_CTX, customer={'name': PAYER}, ac_names=names)
        assert not [t for t in _drawn_text(proforma_pdf.render(ctx)) if t.startswith('A/C')]


_MIN_CTX = {
    'vessel_name': 'ACVESSEL', 'ref_no': 'ZZ/1', 'date_str': '18.09.2026',
    'rows': [{'label': 'Cargo Handling', 'indent': False, 'qty': None, 'rate': None,
              'amount': None, 'cgst_rate': 9, 'sgst_rate': 9, 'igst_rate': 18}],
    'sac_codes': '996719', 'subtotal': 0.0, 'tax_rows': [], 'total': 0.0,
    'amount_words': 'Nil.', 'escalation_note': '', 'seller_gstin': '27AAGCJ3665D1ZK',
    'seller_pan': 'AAGCJ3665D', 'payment_note': 'x',
}


def test_demo_still_renders():
    assert proforma_pdf.demo().startswith(b'%PDF')


# ── Money column ────────────────────────────────────────────────────────────

def test_every_figure_in_the_money_column_carries_paise():
    """A bare '33,557' beside a '2,49,227.50' reads as a different kind of
    number, so the column is written to the paise throughout."""
    assert proforma_pdf.inr(33557) == '33,557.00'
    assert proforma_pdf.inr(33557.7) == '33,557.70'
    assert proforma_pdf.inr(372852.25) == '3,72,852.25'
    assert proforma_pdf.inr(0) == '0.00'
    assert proforma_pdf.inr(None) == '0.00'
    assert proforma_pdf.inr(-1234.5) == '-1,234.50'
    # the covering mail quotes the same figures, so it formats them the same way
    assert views._inr(33557) == '33,557.00'
    assert views._inr(33557.7) == '33,557.70'


def test_gst_is_not_rounded_to_whole_rupees():
    """It used to be, which drifted up to a rupee per line against the amounts
    printed beside it."""
    rows = [{'label': 'x', 'amount': 372852.25,
             'cgst_rate': 9, 'sgst_rate': 9, 'igst_rate': 18}]
    tax = proforma_pdf.tax_lines(rows, intra_state=True)
    # 9% of 3,72,852.25 = 33,556.7025, half up to the paise
    assert [t['amount'] for t in tax] == [33556.70, 33556.70], tax
    assert proforma_pdf.inr(tax[0]['amount']) == '33,556.70'
    # and the total adds up from the printed figures, not from rounded ones
    total = round(372852.25 + sum(t['amount'] for t in tax), 2)
    assert proforma_pdf.inr(total) == '4,39,965.65'


def test_half_up_at_the_paise():
    rows = [{'label': 'x', 'amount': 100.05, 'cgst_rate': 5, 'sgst_rate': 0, 'igst_rate': 0}]
    # 5% of 100.05 = 5.0025 -> 5.00
    assert proforma_pdf.tax_lines(rows, intra_state=True)[0]['amount'] == 5.00
    rows[0]['amount'] = 100.10        # 5% = 5.005 -> 5.01, not 5.00
    assert proforma_pdf.tax_lines(rows, intra_state=True)[0]['amount'] == 5.01
