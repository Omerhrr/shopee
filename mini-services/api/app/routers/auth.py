"""Auth: admin/staff login + password change."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import get_current_admin
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == body.email.strip().lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    token = create_access_token(user.id, user.email, user.role)
    return {"access_token": token, "user": {"email": user.email, "role": user.role}}


@router.get("/me")
def me(admin: models.User = Depends(get_current_admin)):
    """Token validation endpoint used by the admin route middleware."""
    return {"email": admin.email, "role": admin.role}


class PasswordIn(BaseModel):
    current: str
    new: str


@router.post("/change-password")
def change_password(body: PasswordIn, admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    if not verify_password(body.current, admin.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if len(body.new) < 8:
        raise HTTPException(400, "New password must be at least 8 characters")
    admin.password_hash = hash_password(body.new)
    db.commit()
    return {"ok": True}
