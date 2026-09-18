"""SRV02 records must carry a VCN reference; SRV01's stays optional.

Both modules run the same view functions, so the rule has to key off the
module code rather than the screen it came from.
"""
from pathlib import Path

from modules.SRV01 import views as srv_views

TEMPLATE = Path('modules/SRV01/srv01.html').read_text(encoding='utf-8')

HEADER = {'service_type_id': None, 'billable_quantity': 5}


def test_srv02_blocks_a_record_with_no_vcn():
    err = srv_views._approval_blocker(dict(HEADER), [], 'SRV02')
    assert err and 'VCN reference is required' in err


def test_srv02_accepts_a_record_with_a_vcn():
    assert srv_views._approval_blocker(dict(HEADER, ref_source_id=7), [], 'SRV02') is None


def test_srv01_is_unaffected():
    """The reference was always optional here and stays that way."""
    assert srv_views._approval_blocker(dict(HEADER), [], 'SRV01') is None
    # and the default, for any caller that does not pass a code
    assert srv_views._approval_blocker(dict(HEADER), []) is None


def test_both_save_and_approve_enforce_it():
    """A record that cannot be saved as Approved must not slip in through the
    approve endpoint either — the two share this rule on purpose."""
    src = Path('modules/SRV01/views.py').read_text(encoding='utf-8')
    save = src[src.index('def save('):src.index('def _approval_blocker')]
    approve = src[src.index('def approve('):]
    assert '_approval_blocker(header_data, field_values, code)' in save
    assert '_approval_blocker(header, values, _code())' in approve


def test_the_form_says_it_is_required():
    assert 'ref_required' in TEMPLATE
    # no "None" escape hatch on the reference type when it is mandatory
    assert "{% if not ref_required %}<option value=\"\">-- None --</option>{% endif %}" in TEMPLATE
    assert 'REF_REQUIRED && !refSourceId' in TEMPLATE


def test_only_srv02_is_listed_as_requiring_it():
    assert srv_views.REF_REQUIRED == {'SRV02'}
