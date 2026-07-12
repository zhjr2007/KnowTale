from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.course import Course
from app.models.user import User
from app.dependencies import require_user, require_teacher
from app.services.analytics import analyze_conversations, generate_report, get_latest_report
from app.services.role_updater import update_student_roles, trigger_analysis

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/{course_id}")
async def get_analytics(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    report = await get_latest_report(course_id, db=db)
    if report:
        report["course_name"] = course.name
        return report

    data = await analyze_conversations(course_id, days=7, db=db)
    data["course_name"] = course.name
    return data


@router.post("/{course_id}/trigger")
async def trigger_analytics(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    result_data = await trigger_analysis(course_id)
    result_data["report"]["course_name"] = course.name
    return result_data


@router.post("/{course_id}/update-roles")
async def update_roles(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    data = await update_student_roles(course_id, db=db)
    if not data.get("updated"):
        raise HTTPException(status_code=400, detail=data.get("message", "更新失败"))
    return data
