import pytest
from typing import Any, cast

from ssv.policy import PolicyParams


def test_policy_validate_ok_and_coercion():
    p = PolicyParams(
        hash_h='aa'*32,
        borrower_xonly='bb'*32,
        provider_xonly='cc'*32,
        csv_blocks=cast(Any, '10'),  # runtime coercion; cast for type-checker
    )
    p.validate()
    assert isinstance(p.csv_blocks, int)
    assert p.csv_blocks == 10


@pytest.mark.parametrize('field,val', [
    ('hash_h', 'aa'),
    ('borrower_xonly', 'bb'),
    ('provider_xonly', 'cc'),
])
def test_policy_invalid_hex_lengths(field: str, val: str) -> None:
    kwargs: dict[str, Any] = {
        'hash_h': 'aa'*32,
        'borrower_xonly': 'bb'*32,
        'provider_xonly': 'cc'*32,
        'csv_blocks': 10,
    }
    kwargs[field] = val
    p = PolicyParams(**cast(Any, kwargs))
    with pytest.raises(ValueError):
        p.validate()


@pytest.mark.parametrize('csv', [cast(Any, '-1'), -5, 0, 70000])
def test_policy_invalid_csv_blocks(csv: Any) -> None:
    p = PolicyParams(hash_h='aa'*32, borrower_xonly='bb'*32, provider_xonly='cc'*32, csv_blocks=csv)
    with pytest.raises(ValueError):
        p.validate()
