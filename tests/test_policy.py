import pytest

from ssv.policy import PolicyParams


def test_policy_validate_ok_and_coercion():
    p = PolicyParams(
        hash_h='aa'*32,
        borrower_xonly='bb'*32,
        provider_xonly='cc'*32,
        csv_blocks='10',  # coercible
    )
    p.validate()
    assert isinstance(p.csv_blocks, int)
    assert p.csv_blocks == 10


@pytest.mark.parametrize('field,val', [
    ('hash_h', 'aa'),
    ('borrower_xonly', 'bb'),
    ('provider_xonly', 'cc'),
])
def test_policy_invalid_hex_lengths(field, val):
    kwargs = dict(hash_h='aa'*32, borrower_xonly='bb'*32, provider_xonly='cc'*32, csv_blocks=10)
    kwargs[field] = val
    p = PolicyParams(**kwargs)
    with pytest.raises(ValueError):
        p.validate()


@pytest.mark.parametrize('csv', ['-1', -5, 0])
def test_policy_invalid_csv_blocks(csv):
    p = PolicyParams(hash_h='aa'*32, borrower_xonly='bb'*32, provider_xonly='cc'*32, csv_blocks=csv)
    with pytest.raises(ValueError):
        p.validate()

