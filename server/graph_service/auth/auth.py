# """
# API Key generation and authentication dependency for FastAPI.
# """
# from __future__ import annotations

# import hashlib
# import secrets
# from typing import Annotated

# from fastapi import Depends, Header, HTTPException, status

# ## todo user
# ##from graph_service.auth.db import get_user_by_api_key

# # Length of the random part of the API key (prefix "sk-" + 32 bytes hex = 67 chars)
# API_KEY_PREFIX = 'sk-'
# API_KEY_BYTES = 32


# def hash_api_key(key: str) -> str:
#     """Return SHA-256 hash of the API key for storage/comparison."""
#     return hashlib.sha256(key.encode()).hexdigest()


# def generate_api_key() -> str:
#     """Generate a new API key (returned once to the user; store only its hash)."""
#     return API_KEY_PREFIX + secrets.token_hex(API_KEY_BYTES)


# async def get_current_user_optional(
#     x_api_key: Annotated[str | None, Header(alias='X-API-Key')] = None,
#     authorization: str | None = None,
# ) -> dict | None:
#     """
#     Resolve current user from X-API-Key or Authorization: Bearer <key>.
#     Returns None if no key or invalid key (does not raise).
#     """
#     key: str | None = x_api_key
#     if not key and authorization and authorization.startswith('Bearer '):
#         key = authorization[7:].strip()
#     if not key:
#         return None
#     key_hash = hash_api_key(key)
#     user = get_user_by_api_key(key_hash)
#     return user


# async def get_current_user(
#     user: dict | None = Depends(get_current_user_optional),
# ) -> dict:
#     """Require a valid API key; raise 401 if missing or invalid."""
#     if user is None:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail='Missing or invalid API key. Provide X-API-Key header or Authorization: Bearer <key>.',
#         )
#     return user
