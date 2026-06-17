from app.models.crypto import hash_password, new_salt, verify_password


def test_hash_and_verify() -> None:
    salt = new_salt()
    pw = "testPassword123"
    h = hash_password(pw, salt)
    assert verify_password(pw, salt.hex(), h)
    assert not verify_password("wrong", salt.hex(), h)


def test_salt_unique() -> None:
    s1 = new_salt()
    s2 = new_salt()
    assert s1 != s2
