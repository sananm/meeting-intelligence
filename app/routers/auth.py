"""Authentication endpoints for user registration and login."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentUser
from app.services.auth import (
    Token,
    UserCreate,
    UserResponse,
    authenticate_user,
    create_access_token,
    create_user,
    get_user_by_email,
)

router = APIRouter()


class LoginRequest(BaseModel):
    """Request body for login."""
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    """Request body for user registration."""
    email: EmailStr
    password: str
    full_name: str | None = None


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user account.

    Returns the created user (without password).
    """
    # Check if user already exists
    existing_user = await get_user_by_email(db, request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Validate password strength
    if len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long",
        )

    # Create user
    user_data = UserCreate(
        email=request.email,
        password=request.password,
        full_name=request.full_name,
    )
    user = await create_user(db, user_data)

    return user


@router.post("/login", response_model=Token)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Login with email and password.

    Returns a JWT access token.
    """
    user = await authenticate_user(db, request.email, request.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # Create access token
    access_token = create_access_token(data={"sub": str(user.id)})

    return Token(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: CurrentUser,
):
    """
    Get the current authenticated user's information.
    """
    return current_user


class UpdateUserRequest(BaseModel):
    """Request body for updating user profile."""
    full_name: str | None = None


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    request: UpdateUserRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Update the current user's profile.
    """
    if request.full_name is not None:
        current_user.full_name = request.full_name

    await db.commit()
    await db.refresh(current_user)

    return current_user
