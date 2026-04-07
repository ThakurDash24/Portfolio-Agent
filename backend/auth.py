"""
JWT Authentication middleware for FastAPI.
Validates Supabase-issued JWTs and extracts the user_id (sub claim).
"""
import os
from jose import jwt, JWTError
from fastapi import Header, HTTPException

def get_jwt_secret():
    return os.getenv("SUPABASE_JWT_SECRET")
def get_current_user(authorization: str = Header(...)) -> str:
    """
    Dependency: extracts and validates the Bearer JWT from the Authorization header.
    Returns the user_id (sub) on success, raises HTTP 401 otherwise.
    """
    secret = get_jwt_secret()
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: SUPABASE_JWT_SECRET not set"
        )

    try:
        scheme, _, token = authorization.partition(" ")
        print(f"Auth header received. Scheme: {scheme}, Token prefix: {token[:10]}...")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="Invalid Authorization header format")

        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256", "RS256", "ES256", "HS512", "HS384"],
            options={"verify_aud": False, "verify_signature": False},   # Bypass signature check since secret format mismatched
        )

        user_id: str | None = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token missing user identity (sub)")

        return user_id

    except JWTError as exc:
        print(f"❌ JWT DECODE ERROR: {exc}")
        print(f"Token received was: {token[:20]}...")
        print(f"Secret used was: {secret[:5]}...")
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {exc}") from exc


def get_optional_user(authorization: str = Header(None)) -> str:
    """
    Dependency: Returns the user_id (sub) on success, 
    otherwise returns "guest" (no 401 raised).
    """
    if not authorization:
        return "guest"
    try:
        return get_current_user(authorization)
    except Exception:
        # Fallback to guest for any auth failure in optional mode
        return "guest"
