"""Auth router: login with email + verification code."""

from fastapi import APIRouter, HTTPException

from graph_service.dto.auth_dto import LoginRequest, LoginResponse
from graph_service.services.auth_service import login

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login_endpoint(req: LoginRequest) -> LoginResponse:
    result = await login(req.email.strip(), req.code.strip())
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid email or verification code")
    return LoginResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_in=result.expires_in,
    )
