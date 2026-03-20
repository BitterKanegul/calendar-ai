"""
Google OAuth2 Controller

Endpoints for connecting/disconnecting Gmail access.
- GET /auth/google/connect       — returns the Google consent URL
- GET /auth/google/callback      — handles the OAuth2 code exchange
- DELETE /auth/google/disconnect — removes stored credentials
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from utils.jwt import get_user_id_from_token
from mcp_servers.email_auth import get_auth_url, exchange_code, has_gmail_access
from pathlib import Path
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["google-auth"])
security = HTTPBearer()


@router.get("/connect")
async def google_connect(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Return the Google OAuth2 consent URL for the authenticated user.
    The mobile app opens this URL in a browser/WebView.
    """
    try:
        user_id = get_user_id_from_token(credentials.credentials)
        auth_url = get_auth_url(user_id)
        return {"auth_url": auth_url}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/callback")
async def google_callback(code: str, state: str):
    """
    Google redirects here after the user grants consent.
    `state` contains the user_id set in get_auth_url().
    Exchanges the code for tokens and saves them.
    """
    try:
        user_id = int(state)
        exchange_code(user_id, code)
        logger.info(f"Gmail connected for user {user_id}")
        # In production, redirect to the mobile app's deep link or a success page
        return {"message": "Gmail connected successfully. You can close this window."}
    except Exception as e:
        logger.error(f"OAuth2 callback failed: {e}")
        raise HTTPException(status_code=400, detail=f"OAuth2 exchange failed: {e}")


@router.get("/status")
async def gmail_status(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Check whether the current user has connected Gmail."""
    user_id = get_user_id_from_token(credentials.credentials)
    return {"connected": has_gmail_access(user_id)}


@router.delete("/disconnect")
async def google_disconnect(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Remove stored Gmail credentials for the current user."""
    user_id = get_user_id_from_token(credentials.credentials)
    creds_file = Path(settings.GMAIL_CREDENTIALS_DIR) / f"{user_id}.json"
    if creds_file.exists():
        creds_file.unlink()
        logger.info(f"Gmail disconnected for user {user_id}")
    return {"message": "Gmail disconnected."}
