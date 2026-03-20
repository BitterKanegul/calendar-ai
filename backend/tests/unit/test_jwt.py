"""Tests for JWT token creation and verification."""
import pytest
from datetime import timedelta, timezone, datetime
from unittest.mock import patch
from fastapi import HTTPException

from utils.jwt import (
    create_access_token,
    create_refresh_token,
    verify_token,
    verify_refresh_token,
    get_user_id_from_token,
)


def test_create_access_token_returns_string():
    token = create_access_token({"user_id": 1})
    assert isinstance(token, str)
    assert len(token) > 20

def test_create_refresh_token_returns_string():
    token = create_refresh_token({"user_id": 1})
    assert isinstance(token, str)

def test_verify_valid_access_token():
    token = create_access_token({"user_id": 42})
    data = verify_token(token)
    assert data.user_id == 42

def test_verify_expired_access_token():
    token = create_access_token({"user_id": 1}, expires_delta=timedelta(seconds=-1))
    with pytest.raises(HTTPException) as exc:
        verify_token(token)
    assert exc.value.status_code == 401

def test_verify_refresh_token_rejects_access_token():
    """verify_refresh_token should reject a token typed 'access'."""
    access_token = create_access_token({"user_id": 1})
    with pytest.raises(HTTPException) as exc:
        verify_refresh_token(access_token)
    assert exc.value.status_code == 401

def test_verify_access_token_rejects_refresh_token():
    """verify_token should reject a token typed 'refresh'."""
    refresh_token = create_refresh_token({"user_id": 1})
    with pytest.raises(HTTPException) as exc:
        verify_token(refresh_token)
    assert exc.value.status_code == 401

def test_get_user_id_from_token():
    token = create_access_token({"user_id": 99})
    uid = get_user_id_from_token(token)
    assert uid == 99

def test_verify_token_invalid_signature():
    token = create_access_token({"user_id": 1})
    tampered = token[:-4] + "XXXX"
    with pytest.raises(HTTPException) as exc:
        verify_token(tampered)
    assert exc.value.status_code == 401
