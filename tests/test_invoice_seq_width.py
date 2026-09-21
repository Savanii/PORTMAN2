"""A Start At typed as "0418" numbers invoices 0418, not 418.

Start At is stored as an integer, so the leading zero had nowhere to live and
the invoice went out as PREFIX/418. The number was always right; the width was
what got lost. seq_width carries it.

Pure functions -- no DB.
"""
import pytest

from modules.FIN01.model import format_doc_seq
from modules.INVDS01.model import _start_seq


# ── What the operator typed ─────────────────────────────────────────────────

def test_a_leading_zero_sets_the_width():
    assert _start_seq('0418') == (418, 4)


def test_no_leading_zero_asks_for_no_padding():
    # Existing series must be unaffected, so plain input stores width None.
    assert _start_seq('418') == (418, None)


def test_several_leading_zeros_keep_the_full_width():
    assert _start_seq('000418') == (418, 6)


def test_blank_and_zero_mean_no_cut_off():
    for v in (None, '', '  ', '0'):
        assert _start_seq(v) == (None, None), v


def test_an_integer_still_works():
    # The grid can hand back a number once a row has been saved and reloaded.
    assert _start_seq(418) == (418, None)


def test_surrounding_whitespace_is_ignored():
    assert _start_seq('  0418  ') == (418, 4)


def test_rubbish_is_refused():
    for v in ('abc', '4.18', '4a18'):
        with pytest.raises(ValueError):
            _start_seq(v)


def test_below_one_is_refused():
    with pytest.raises(ValueError):
        _start_seq('-5')


# ── What gets printed ───────────────────────────────────────────────────────

def test_the_sequence_is_padded_to_the_width():
    assert format_doc_seq(418, 4) == '0418'


def test_no_width_prints_plain():
    assert format_doc_seq(418, None) == '418'


def test_padding_continues_as_the_series_runs():
    # 0418 -> 0419 -> ... the width holds for every later number, which is the
    # whole point: one invoice padded and the next not would look like two
    # different series.
    assert [format_doc_seq(n, 4) for n in (418, 419, 999, 1000)] == \
        ['0418', '0419', '0999', '1000']


def test_a_number_wider_than_the_width_is_never_truncated():
    # Past 9999 on a 4-wide series it simply prints wider -- silently dropping
    # a digit would issue a duplicate invoice number.
    assert format_doc_seq(10000, 4) == '10000'


def test_width_zero_is_treated_as_no_padding():
    assert format_doc_seq(418, 0) == '418'
