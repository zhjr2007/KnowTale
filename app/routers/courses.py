from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models.course import Course, CourseEnrollment
from app.models.user import User
from app.dependencies import require_user, require_teacher

router = APIRouter(prefix="/api/courses", tags=["courses"])


class CreateCourseRequest(BaseModel):
    name: str
    description: str = ""


@router.get("")
async def list_courses(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role == "teacher":
        result = await db.execute(
            select(Course).where(Course.teacher_id == user.id)
            .order_by(Course.created_at.desc())
        )
        courses = result.scalars().all()
    else:
        result = await db.execute(
            select(Course).join(CourseEnrollment)
            .where(
                CourseEnrollment.student_id == user.id,
                CourseEnrollment.status == "approved",
            )
            .order_by(CourseEnrollment.enrolled_at.desc())
        )
        courses = result.scalars().all()

    result_list = []
    for c in courses:
        count_result = await db.execute(
            select(func.count(CourseEnrollment.id))
            .where(
                CourseEnrollment.course_id == c.id,
                CourseEnrollment.status == "approved",
            )
        )
        student_count = count_result.scalar() or 0
        result_list.append({
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "teacher_id": c.teacher_id,
            "student_count": student_count,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })

    return result_list


@router.post("")
async def create_course(
    req: CreateCourseRequest,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    course = Course(
        name=req.name,
        description=req.description,
        teacher_id=user.id,
    )
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return {"id": course.id, "name": course.name, "description": course.description}


@router.get("/{course_id}")
async def get_course(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    if user.role == "student":
        enrollment_result = await db.execute(
            select(CourseEnrollment).where(
                CourseEnrollment.course_id == course_id,
                CourseEnrollment.student_id == user.id,
                CourseEnrollment.status == "approved",
            )
        )
        if not enrollment_result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="未加入该课程")

    teacher_result = await db.execute(select(User).where(User.id == course.teacher_id))
    teacher = teacher_result.scalar_one_or_none()

    return {
        "id": course.id,
        "name": course.name,
        "description": course.description,
        "teacher_name": teacher.display_name if teacher else "未知",
        "created_at": course.created_at.isoformat() if course.created_at else None,
    }


@router.post("/{course_id}/join")
async def join_course(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role != "student":
        raise HTTPException(status_code=403, detail="仅学生可加入课程")

    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    existing = await db.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.student_id == user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="已申请或已加入该课程")

    enrollment = CourseEnrollment(
        course_id=course_id,
        student_id=user.id,
        status="pending",
    )
    db.add(enrollment)
    await db.commit()

    return {"message": "已发送入班申请，等待老师审批"}
