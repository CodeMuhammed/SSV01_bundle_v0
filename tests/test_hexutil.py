import io
import os
import tempfile

from ssv.hexutil import parse_hex, file_or_hex


def test_parse_hex_valid_and_length():
    b = parse_hex('x', '00ff', length=2)
    assert b == bytes.fromhex('00ff')


def test_parse_hex_invalid_raises():
    try:
        parse_hex('x', 'zz')
        assert False, 'expected error'
    except ValueError:
        pass


def test_file_or_hex_precedence_and_file_reading():
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, 'h.txt')
        with open(p, 'wt') as f:
            f.write('0a')
        # hex arg takes precedence
        assert file_or_hex('x', 'ff', p) == b'\xff'
        # file path used when hex not provided
        assert file_or_hex('x', None, p) == b'\x0a'

