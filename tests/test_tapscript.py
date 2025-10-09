import pytest

from ssv.tapscript import build_tapscript, tapleaf_hash, tapleaf_hash_tagged, disasm


def test_build_tapscript_and_hashes():
    # Deterministic vector (synthetic)
    h = '00' * 32
    pb = '11' * 32
    pp = '22' * 32
    csv = 10

    script = build_tapscript(h, pb, csv, pp)
    # Expected values captured from reference run
    exp_script_hex = (
        '63'  # OP_IF
        'a8' '20' + ('00' * 32) + '88'  # OP_SHA256 <h> OP_EQUALVERIFY
        '20' + ('11' * 32) + 'ac'       # <pk_b> OP_CHECKSIG
        '67'                            # OP_ELSE
        '01' '0a' 'b2' '75'             # <10> CSV OP_DROP
        '20' + ('22' * 32) + 'ac'       # <pk_p> OP_CHECKSIG
        '68'                            # OP_ENDIF
    )
    assert script.hex() == exp_script_hex

    leaf_simple = tapleaf_hash(script)
    leaf_tagged = tapleaf_hash_tagged(script)
    assert leaf_simple.hex() == '26de55a161a9642fc3e02d02392b6e44b8570ee25355ce2b216834e71bfa189d'
    assert leaf_tagged.hex() == '0f134db24bddd4bf87721c526882c45f7d065a0a2df33287a30a09395280da94'

    # Basic disasm sanity
    d = disasm(script)
    assert 'OP_IF' in d and 'OP_ELSE' in d and 'OP_ENDIF' in d


def test_build_tapscript_rejects_large_csv():
    h = '00' * 32
    pb = '11' * 32
    pp = '22' * 32
    with pytest.raises(ValueError):
        build_tapscript(h, pb, 70000, pp)
