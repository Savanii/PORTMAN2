"""sap_builder.build_invoice_payload produces the expected SAP/PORTBIRD payload
shape. Hits the dev DB (via get_active_config / finance_service_types) like the
rest of this suite; no network call to SAP itself."""
import sap_builder


def test_build_invoice_payload_shape():
    header = {
        'invoice_number': 'INV-TST-1', 'invoice_date': '2026-07-02',
        'customer_type': 'Customer', 'customer_id': 1, 'customer_name': 'ACME',
        'customer_gstin': '27ABCDE1234F1Z5', 'customer_gst_state_code': '27',
        'subtotal': 10000, 'cgst_amount': 900, 'sgst_amount': 900, 'igst_amount': 0,
        'total_amount': 11800,
    }
    lines = [{
        'service_code': 'CHGU01', 'service_name': 'Cargo Handling Unloading',
        'quantity': 100, 'rate': 100, 'line_amount': 10000, 'sac_code': '996719',
        'gst_rate_id': 4, 'cgst_amount': 900, 'sgst_amount': 900, 'igst_amount': 0,
        'gl_code': '4101076030',
    }]
    payload = sap_builder.build_invoice_payload(header, lines)
    assert isinstance(payload, dict)

    # Envelope: { "Record_Header": [ {...header..., "ITEM": [...] } ] } (PORTBIRD spec).
    assert 'Record_Header' in payload
    records = payload['Record_Header']
    assert len(records) == 1
    record = records[0]

    # Header contract (build_invoice_payload): Invoice_Credit='I',
    # Document_type='DR' (SAP doc type for Invoice/Debit Note).
    assert record['Invoice_Credit'] == 'I'
    assert record['Document_type'] == 'DR'
    assert record['Reference'] == 'INV-TST-1'
    assert record['Cancellation_Flag'] == ''
    assert record['Nature_of_transaction'] == 'B2B'  # GSTIN present
    assert record['Currency'] == 'INR'

    # ITEM array reflects the single line.
    items = record['ITEM']
    assert items and len(items) == 1
    item = items[0]
    assert item['Reference'] == 'INV-TST-1'
    assert item['Amount'] == '10000.00'
    assert item['CGST_AMT'] == '900.00'
    assert item['SGST_AMT'] == '900.00'
    assert item['IGST_AMT'] == ''
    assert item['HSN_SAC'] == '996719'
