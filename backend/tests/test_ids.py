import uuid

from hypothesis import given
from hypothesis import strategies as st

from app.core.ids import uuid7


def test_uuid7_version_and_variant() -> None:
    value = uuid7()
    assert value.version == 7
    assert value.variant == uuid.RFC_4122


@given(st.integers(min_value=2, max_value=5000))
def test_uuid7_is_strictly_increasing(count: int) -> None:
    ids = [uuid7() for _ in range(count)]
    assert ids == sorted(ids)
    assert len(set(ids)) == count
