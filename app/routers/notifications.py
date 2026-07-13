from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_user
from app.models.user import User
from app.models.notification import Notification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    page: int = 1,
    page_size: int = 20,
    unread_only: bool = False,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.is_read == 0)
    query = query.order_by(Notification.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    notifications = result.scalars().all()

    count_query = select(func.count(Notification.id)).where(Notification.user_id == user.id)
    if unread_only:
        count_query = count_query.where(Notification.is_read == 0)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    unread_result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id, Notification.is_read == 0
        )
    )
    unread_count = unread_result.scalar() or 0

    return {
        "notifications": [
            {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "content": n.content,
                "is_read": n.is_read,
                "course_id": n.course_id,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifications
        ],
        "total": total,
        "unread_count": unread_count,
        "page": page,
    }


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="通知不存在")

    notification.is_read = 1
    await db.commit()
    return {"success": True}


@router.post("/read-all")
async def mark_all_read(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id,
            Notification.is_read == 0,
        )
    )
    count = result.scalar() or 0

    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read == 0)
        .values(is_read=1)
    )
    await db.commit()
    return {"success": True, "updated_count": count}
