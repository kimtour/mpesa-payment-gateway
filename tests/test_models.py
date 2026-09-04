import pytest

from app.models import normalize_phone


@pytest.mark.parametrize(
    ("input_phone", "expected"),
    [
        ("0712345678", "254712345678"),
        ("712345678", "254712345678"),
        ("254712345678", "254712345678"),
        ("+254 712 345 678", "254712345678"),
    ],
)
def test_normalize_phone(input_phone, expected):
    assert normalize_phone(input_phone) == expected


def test_rejects_invalid_phone():
    with pytest.raises(ValueError):
        normalize_phone("12345")
