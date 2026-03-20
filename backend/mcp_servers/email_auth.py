"""
Gmail OAuth2 Authentication Helper

Manages per-user Gmail credentials using Google's OAuth2 flow.
Credentials (including refresh tokens) are stored per-user as JSON
in GMAIL_CREDENTIALS_DIR (./data/gmail_credentials/{user_id}.json).

On first use for a user, call `get_auth_url()` to start the consent flow,
then `exchange_code()` to trade the authorization code for tokens.
Subsequent calls to `get_gmail_credentials()` auto-refresh expired tokens.
"""
import json
import os
import logging
from typing import Optional
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request

from config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _creds_path(user_id: int) -> Path:
    path = Path(settings.GMAIL_CREDENTIALS_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{user_id}.json"


def get_gmail_credentials(user_id: int) -> Optional[Credentials]:
    """
    Load and (if needed) refresh Gmail credentials for a user.
    Returns None if no credentials exist yet for this user.
    """
    creds_file = _creds_path(user_id)
    if not creds_file.exists():
        return None

    try:
        creds = Credentials.from_authorized_user_file(str(creds_file), SCOPES)
    except Exception as e:
        logger.warning(f"Failed to load credentials for user {user_id}: {e}")
        return None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(user_id, creds)
        except Exception as e:
            logger.warning(f"Failed to refresh credentials for user {user_id}: {e}")
            return None

    return creds if (creds and creds.valid) else None


def _save_credentials(user_id: int, creds: Credentials) -> None:
    creds_file = _creds_path(user_id)
    creds_file.write_text(creds.to_json())


def get_auth_url(user_id: int) -> str:
    """
    Generate the Google OAuth2 consent URL for a user.
    The user must visit this URL in a browser to grant access.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured.")

    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )
    # Store user_id in state so the callback can associate tokens with the user
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=str(user_id),
        prompt="consent",
    )
    return auth_url


def exchange_code(user_id: int, code: str) -> Credentials:
    """
    Exchange an authorization code for tokens and save them.
    Called from the OAuth2 callback endpoint.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured.")

    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    _save_credentials(user_id, creds)
    return creds


def has_gmail_access(user_id: int) -> bool:
    """Check if a user has valid Gmail credentials."""
    return get_gmail_credentials(user_id) is not None
