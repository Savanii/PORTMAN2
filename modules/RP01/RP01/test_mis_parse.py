"""Self-check for the MIS CSV parser: python -m modules.RP01.RP01.test_mis_parse"""
from modules.RP01.RP01.views import parse_mis_csv, MIS_COLUMNS

HDR = ','.join(f'"{h}"' for h, _ in MIS_COLUMNS)

# vessel first row + continuation row (blank vessel cells) + subtotal row (no customer)
GOOD = HDR + '''
2024-25,Nov-24,Nov-24,Q5928,MT WISDOM STAR,Cargill India,NARENDRA FWD,Edible Oil,Edible Oil,Edible Oil,EDIBLE OIL,10/11/24 19:00,14/11/24 02:00,GBL,"12,000.000",Overseas,Import,252,3024000,100,1200000,24.2,290400,Interocean,10000,,,,Cargill India Pvt. Ltd.
,,,,,Reliance Consumer,NARENDRA FWD,Edible Oil,Edible Oil,EDIBLE OIL,,,,Suraj,10000.000,Overseas,Import,252,2520000,100,1000000,24.2,242000,,,,,#N/A,Reliance Consumer Products Ltd.
,,,,,,,,,,,,,,48469.946,,,,12214426,,4846995,,1172973,,30000,,,,
'''

BAD = HDR + '''
2024-25,Nov-24,Nov-24,Q5928,MT SHIP,Cargill,NF,EO,EO,EO,EO,not-a-date,,GBL,12x00,Overseas,Import,,,,,,,,,,,,
'''


def demo():
    rows, errors = parse_mis_csv(GOOD)
    assert errors == [], errors
    assert len(rows) == 2, f'subtotal row not skipped: {len(rows)}'
    r1, r2 = rows
    assert r1['operation_start'] == '2024-11-10T19:00'
    assert r1['quantity'] == 12000.0, 'comma number'
    assert r2['vcn_no'] == 'Q5928' and r2['vessel_name'] == 'MT WISDOM STAR', 'forward-fill'
    assert r2['operation_start'] == '2024-11-10T19:00', 'forward-fill dates'
    assert r2['gangway_amount'] is None, 'gangway must not forward-fill'
    assert r2['remarks'] is None, '#N/A treated as blank'

    rows, errors = parse_mis_csv(BAD)
    assert any('operation_start' in e for e in errors), errors
    assert any('quantity' in e for e in errors), errors

    rows, errors = parse_mis_csv('"Wrong Header"\nx')
    assert errors and 'Missing columns' in errors[0]
    print('mis parse self-check OK')


if __name__ == '__main__':
    demo()
