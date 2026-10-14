import pytest

from lingard_api.auth.pin import PinHasher, generate_pin, normalise_name, pin_weakness, validate_display_name


@pytest.mark.parametrize(
    "pin", ["000000", "123456", "654321", "890123", "111222", "121212", "123123", "112233", "123321", "12345", "12a456"]
)
def test_weak_pins_rejected(pin: str) -> None:
    assert pin_weakness(pin) is not None


@pytest.mark.parametrize("pin", ["613470", "730264", "195837"])
def test_reasonable_pins_accepted(pin: str) -> None:
    assert pin_weakness(pin) is None


def test_generated_pins_are_strong() -> None:
    assert all(pin_weakness(generate_pin()) is None for _ in range(200))


def test_name_normalisation_is_unicode_and_case_insensitive() -> None:
    assert normalise_name("Ernest") == normalise_name("ERNEST") == normalise_name("Ｅｒｎｅｓｔ")
    assert normalise_name("  Wizzy   B ") == "wizzy b"
    with pytest.raises(ValueError):
        validate_display_name("x")


def test_hasher_uses_argon2id_with_unique_salts() -> None:
    hasher = PinHasher(time_cost=1, memory_kib=8, parallelism=1)
    a, b = hasher.hash("613470"), hasher.hash("613470")
    assert a.startswith("$argon2id$") and a != b
    assert hasher.verify(a, "613470") and not hasher.verify(a, "613471")
    assert not hasher.verify("garbage", "613470")
