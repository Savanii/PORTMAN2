"""The FINV01 invoice items table and GST rows are structured like the pro
forma: a heading per cargo service with one row per cargo underneath, service
charges flat, and one GST row per rate actually charged.

Pure helpers over in-memory dicts — no DB.
"""
from modules.FINV01.views import (
    _group_cargo_lines, _flat_service_lines, _gst_rate_lines)


def _cargo(service_code, service_name, cargo_name, qty, rate, **extra):
    line = {'service_code': service_code, 'service_name': service_name,
            'cargo_name': cargo_name, 'quantity': qty, 'rate': rate,
            'line_amount': round(qty * rate, 2), 'sac_code': '996719',
            'uom': 'MT', 'cargo_source_id': 1}
    line.update(extra)
    return line


# --- Cargo grouping ---------------------------------------------------------

def test_service_becomes_heading_with_cargo_rows_underneath():
    rows = _group_cargo_lines([
        _cargo('CHGU01', 'Cargo Handling Unloading', 'COAL', 100.0, 50.0),
        _cargo('CHGU01', 'Cargo Handling Unloading', 'COKE', 40.0, 60.0),
    ])
    assert [r['service_name'] for r in rows] == [
        'Cargo Handling Unloading', 'COAL', 'COKE']
    assert rows[0]['is_heading'] is True
    # The heading carries no figures, so it cannot double-count into Sub Total.
    assert rows[0]['line_amount'] is None
    assert rows[1]['indent'] is True and rows[1]['line_amount'] == 5000.00
    assert rows[2]['line_amount'] == 2400.00


def test_same_cargo_across_parcels_merges_at_one_rate():
    rows = _group_cargo_lines([
        _cargo('CHGU01', 'Cargo Handling Unloading', 'COAL', 100.0, 50.0),
        _cargo('CHGU01', 'Cargo Handling Unloading', 'COAL', 60.0, 50.0),
    ])
    detail = [r for r in rows if not r['is_heading']]
    assert len(detail) == 1
    assert detail[0]['quantity'] == 160.0
    assert detail[0]['line_amount'] == 8000.00


def test_same_cargo_at_two_rates_keeps_separate_rows():
    # Averaging these into one row would print a rate nobody was charged.
    rows = _group_cargo_lines([
        _cargo('CHGU01', 'Cargo Handling Unloading', 'COAL', 100.0, 50.0),
        _cargo('CHGU01', 'Cargo Handling Unloading', 'COAL', 100.0, 70.0),
    ])
    detail = [r for r in rows if not r['is_heading']]
    assert len(detail) == 2
    assert sorted(r['rate'] for r in detail) == [50.0, 70.0]


def test_grouped_rows_sum_to_the_line_total():
    lines = [
        _cargo('CHGU01', 'Cargo Handling Unloading', 'COAL', 100.0, 50.0),
        _cargo('INFM01', 'Infrastructure', 'COAL', 100.0, 10.0),
        _cargo('CHGU01', 'Cargo Handling Unloading', 'COKE', 40.0, 60.0),
    ]
    rows = _group_cargo_lines(lines)
    assert round(sum(r['line_amount'] or 0 for r in rows), 2) == \
        round(sum(l['line_amount'] for l in lines), 2)


# --- Service charges --------------------------------------------------------

def test_service_lines_stay_flat_and_merge_per_rate():
    rows = _flat_service_lines([
        {'service_name': 'Shore Gangway', 'quantity': 2, 'rate': 500.0,
         'line_amount': 1000.0, 'sac_code': '9967'},
        {'service_name': 'Shore Gangway', 'quantity': 3, 'rate': 500.0,
         'line_amount': 1500.0, 'sac_code': '9967'},
        {'service_name': 'Shore Gangway', 'quantity': 1, 'rate': 800.0,
         'line_amount': 800.0, 'sac_code': '9967'},
    ])
    assert len(rows) == 2
    assert not any(r['is_heading'] for r in rows)
    assert rows[0]['quantity'] == 5.0 and rows[0]['line_amount'] == 2500.00
    assert rows[1]['rate'] == 800.0


# --- GST rows ---------------------------------------------------------------

def test_one_gst_row_per_rate_not_a_blended_percentage():
    # 18% cargo handling next to 0%-rated toll. Back-computing one percentage
    # from cgst_amount / subtotal printed "CGST 6%", which is not a GST rate.
    lines = [
        {'cgst_rate': 9, 'sgst_rate': 9, 'igst_rate': 0,
         'cgst_amount': 900.0, 'sgst_amount': 900.0, 'igst_amount': 0.0},
        {'cgst_rate': 0, 'sgst_rate': 0, 'igst_rate': 0,
         'cgst_amount': 0.0, 'sgst_amount': 0.0, 'igst_amount': 0.0},
    ]
    rows = _gst_rate_lines(lines)
    assert [r['label'] for r in rows] == ['CGST 9%', 'SGST 9%']
    assert [r['amount'] for r in rows] == [900.0, 900.0]


def test_two_gst_rates_print_as_two_rows_each():
    lines = [
        {'cgst_rate': 9, 'sgst_rate': 9, 'cgst_amount': 900.0, 'sgst_amount': 900.0},
        {'cgst_rate': 2.5, 'sgst_rate': 2.5, 'cgst_amount': 250.0, 'sgst_amount': 250.0},
    ]
    rows = _gst_rate_lines(lines)
    assert [r['label'] for r in rows] == [
        'CGST 2.5%', 'CGST 9%', 'SGST 2.5%', 'SGST 9%']
    assert round(sum(r['amount'] for r in rows), 2) == 2300.00


def test_interstate_prints_igst_only():
    rows = _gst_rate_lines([
        {'igst_rate': 18, 'igst_amount': 1800.0,
         'cgst_rate': 0, 'sgst_rate': 0, 'cgst_amount': 0.0, 'sgst_amount': 0.0},
    ])
    assert [r['label'] for r in rows] == ['IGST 18%']


def test_no_gst_prints_nothing():
    assert _gst_rate_lines([
        {'cgst_rate': 0, 'sgst_rate': 0, 'igst_rate': 0,
         'cgst_amount': 0.0, 'sgst_amount': 0.0, 'igst_amount': 0.0},
    ]) == []
