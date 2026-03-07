# """
# Auth router: register user, create API key.
# """
# from fastapi import APIRouter, HTTPException, status
# from pydantic import BaseModel, Field

# from graph_service.auth.auth import generate_api_key, hash_api_key
# from graph_service.auth.db import create_api_key, create_user, init_db

# router = APIRouter()


# class RegisterRequest(BaseModel):
#     username: str = Field(..., min_length=1, description='Username for the new user')


# class RegisterResponse(BaseModel):
#     user_id: str
#     username: str
#     api_key: str = Field(..., description='API key (only returned once; store securely)')


# @router.post('/auth/register', status_code=status.HTTP_201_CREATED, response_model=RegisterResponse)
# async def register(request: RegisterRequest):
#     """Create a user and return an API key. The key is only shown once."""
#     init_db()
#     try:
#         user = create_user(request.username)
#     except Exception as e:
#         if 'UNIQUE' in str(e) or 'unique' in str(e).lower():
#             raise HTTPException(
#                 status_code=status.HTTP_409_CONFLICT,
#                 detail=f'Username "{request.username}" already exists',
#             ) from e
#         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
#     api_key = generate_api_key()
#     key_hash = hash_api_key(api_key)
#     create_api_key(user_id=user['id'], key_hash=key_hash, name='default')
#     return RegisterResponse(
#         user_id=user['id'],
#         username=user['username'],
#         api_key=api_key,
#     )
