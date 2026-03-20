"""Tests for password hashing and verification."""
import pytest
from utils.password import get_password_hash, verify_password


def test_hash_returns_string():
    hashed = get_password_hash("mysecret")
    assert isinstance(hashed, str)
    assert len(hashed) > 20

def test_verify_correct_password():
    hashed = get_password_hash("mysecret")
    assert verify_password("mysecret", hashed) is True

def test_verify_wrong_password():
    hashed = get_password_hash("mysecret")
    assert verify_password("wrongpassword", hashed) is False

def test_hash_is_nondeterministic():
    """bcrypt generates different hashes for the same password."""
    h1 = get_password_hash("same_password")
    h2 = get_password_hash("same_password")
    assert h1 != h2
    # But both should verify correctly
    assert verify_password("same_password", h1) is True
    assert verify_password("same_password", h2) is True
