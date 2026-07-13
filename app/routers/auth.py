from pathlib import Path
from fastapi import APIRouter, Request, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import bcrypt
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.models.user import User
from app.dependencies import create_access_token, get_current_user, require_user, require_teacher

AVATARS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "avatars"
AVATARS_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = "student"
    display_name: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class ResetPasswordRequest(BaseModel):
    user_id: int
    new_password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(User).where(
            (User.username == req.username) | (User.email == req.email)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名或邮箱已存在")

    user = User(
        username=req.username,
        email=req.email,
        hashed_password=_hash_password(req.password),
        role=req.role if req.role in ("teacher", "student") else "student",
        display_name=req.display_name or req.username,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id, user.role)
    resp = RedirectResponse(url="/dashboard", status_code=302)
    resp.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=3600 * 24 * 7,
        samesite="lax",
    )
    return resp


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if not user or not _verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(user.id, user.role)
    resp = RedirectResponse(url="/dashboard", status_code=302)
    resp.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=3600 * 24 * 7,
        samesite="lax",
    )
    return resp


@router.post("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie(key="access_token")
    return resp


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "display_name": user.display_name,
    }


@router.post("/reset-password")
async def reset_password(
    req: ResetPasswordRequest,
    teacher: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == req.user_id))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="用户不存在")
    student.hashed_password = _hash_password(req.new_password)
    await db.commit()
    return {"message": "密码已重置"}


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if not _verify_password(req.old_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="旧密码错误")
    user.hashed_password = _hash_password(req.new_password)
    await db.commit()
    return {"message": "密码已修改"}


@router.post("/user/profile/update")
async def update_profile(
    display_name: str = Form(None),
    avatar: UploadFile = File(None),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if display_name is not None:
        display_name = display_name.strip()
        if display_name:
            user.display_name = display_name

    if avatar:
        ext = Path(avatar.filename).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            return JSONResponse(status_code=400, content={"detail": "仅支持 jpg/png/gif/webp 格式的图片"})
        content = await avatar.read()
        if len(content) > 2 * 1024 * 1024:
            return JSONResponse(status_code=400, content={"detail": "头像文件大小不能超过 2MB"})
        from datetime import datetime
        filename = f"{user.id}_{int(datetime.utcnow().timestamp())}{ext}"
        save_path = AVATARS_DIR / filename
        save_path.write_bytes(content)
        user.avatar = f"/uploads/avatars/{filename}"

    await db.commit()
    await db.refresh(user)
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "avatar": user.avatar,
        "role": user.role,
        "email": user.email,
    }


@router.get("/user/profile")
async def get_profile(
    user: User = Depends(require_user),
):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "display_name": user.display_name,
        "avatar": user.avatar,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
