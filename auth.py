"""
Authentication module: JWT tokens, password hashing, user dependency.
"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select
from database import get_session
from models import User
import os

# Load from .env or use defaults for dev
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Password hashing with argon2
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plain-text password."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    # Convert sub to string for JWT compatibility
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    token: Optional[str], session: Session = Depends(get_session)
) -> User:
    """
    Dependency to validate JWT token and return the current user.
    Raises HTTP 401 if token is invalid or user not found.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = int(payload.get("sub"))  # Convert string back to int
        if user_id is None:
            print(f"DEBUG: Token payload missing 'sub': {payload}")
            raise credentials_exception
    except JWTError as e:
        print(f"DEBUG: JWTError during decode: {str(e)}")
        raise credentials_exception
    except ValueError as e:
        print(f"DEBUG: ValueError converting user_id to int: {str(e)}")
        raise credentials_exception
    except Exception as e:
        print(f"DEBUG: Unexpected error during token decode: {str(e)}")
        raise credentials_exception

    statement = select(User).where(User.id == user_id)
    user = session.exec(statement).first()
    if user is None:
        print(f"DEBUG: User ID {user_id} not found in database")
        raise credentials_exception
    print(f"DEBUG: Successfully authenticated user: {user.username}")
    return user


async def get_current_user_optional(
    session: Session = Depends(get_session), token: Optional[str] = None
) -> Optional[User]:
    """
    Optional auth dependency: returns user if valid token, None otherwise.
    """
    if not token:
        return None
    try:
        return await get_current_user(token, session)
    except HTTPException:
        return None
