from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from typing import List
from database import get_session
from models import (
    User, UserCreate, UserRead, UserUpdate
)

router = APIRouter()

@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, session: Session = Depends(get_session)):
    """Create a new user"""
    # Check if username or email already exists
    existing_user = session.exec(
        select(User).where(
            (User.username == user.username) | (User.email == user.email)
        )
    ).first()
    
    if existing_user:
        if existing_user.username == user.username:
            raise HTTPException(status_code=400, detail="Username already exists")
        else:
            raise HTTPException(status_code=400, detail="Email already exists")
    
    db_user = User.model_validate(user)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user

@router.get("/", response_model=List[UserRead])
def get_users(
    skip: int = 0, 
    limit: int = 100, 
    session: Session = Depends(get_session)
):
    """Get all users"""
    statement = select(User).offset(skip).limit(limit)
    users = session.exec(statement).all()
    return users

@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, session: Session = Depends(get_session)):
    """Get a specific user by ID"""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.get("/username/{username}", response_model=UserRead)
def get_user_by_username(username: str, session: Session = Depends(get_session)):
    """Get a user by username"""
    user = session.exec(select(User).where(User.username == username)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.put("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int, 
    user_update: UserUpdate, 
    session: Session = Depends(get_session)
):
    """Update a user"""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_data = user_update.model_dump(exclude_unset=True)
    
    # Check for username/email conflicts if they're being updated
    if "username" in user_data:
        existing_user = session.exec(
            select(User).where(
                (User.username == user_data["username"]) & (User.id != user_id)
            )
        ).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already exists")
    
    if "email" in user_data:
        existing_user = session.exec(
            select(User).where(
                (User.email == user_data["email"]) & (User.id != user_id)
            )
        ).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already exists")
    
    for field, value in user_data.items():
        setattr(user, field, value)
    
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, session: Session = Depends(get_session)):
    """Delete a user"""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    session.delete(user)
    session.commit()
    return None

@router.patch("/{user_id}/deactivate", response_model=UserRead)
def deactivate_user(user_id: int, session: Session = Depends(get_session)):
    """Deactivate a user"""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_active = False
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

@router.patch("/{user_id}/activate", response_model=UserRead)
def activate_user(user_id: int, session: Session = Depends(get_session)):
    """Activate a user"""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_active = True
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
