import random
import string

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models.course import Course, CourseEnrollment
from app.models.user import User
from app.dependencies import require_user, require_teacher

router = APIRouter(prefix="/api/courses", tags=["courses"])


def _generate_invite_code() -> str:
    return ''.join(random.choices(string.digits, k=6))


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
    invite_code = _generate_invite_code()
    while True:
        existing = await db.execute(
            select(Course).where(Course.invite_code == invite_code)
        )
        if not existing.scalar_one_or_none():
            break
        invite_code = _generate_invite_code()

    course = Course(
        name=req.name,
        description=req.description,
        teacher_id=user.id,
        invite_code=invite_code,
    )
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return {
        "id": course.id,
        "name": course.name,
        "description": course.description,
        "invite_code": course.invite_code,
    }


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

    is_teacher = user.role == "teacher" and course.teacher_id == user.id

    return {
        "id": course.id,
        "name": course.name,
        "description": course.description,
        "teacher_name": teacher.display_name if teacher else "未知",
        "is_teacher": is_teacher,
        "invite_code": course.invite_code if is_teacher else None,
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


@router.post("/join-by-invite")
async def join_course_by_invite(
    invite_code: str = Query(..., description="6位邀请码"),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role != "student":
        raise HTTPException(status_code=403, detail="仅学生可加入课程")

    result = await db.execute(
        select(Course).where(Course.invite_code == invite_code)
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="邀请码无效")

    existing = await db.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.course_id == course.id,
            CourseEnrollment.student_id == user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="已申请或已加入该课程")

    enrollment = CourseEnrollment(
        course_id=course.id,
        student_id=user.id,
        status="pending",
    )
    db.add(enrollment)
    await db.commit()

    return {"message": "已发送入班申请，等待老师审批", "course_id": course.id, "course_name": course.name}


@router.get("/{course_id}/invite-code")
async def get_invite_code(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="只能查看自己课程的邀请码")

    return {"invite_code": course.invite_code}


@router.post("/{course_id}/invite-code/refresh")
async def refresh_invite_code(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="只能刷新自己课程的邀请码")

    new_code = _generate_invite_code()
    while True:
        existing = await db.execute(
            select(Course).where(Course.invite_code == new_code)
        )
        if not existing.scalar_one_or_none():
            break
        new_code = _generate_invite_code()

    course.invite_code = new_code
    await db.commit()
    return {"invite_code": course.invite_code}


@router.get("/{course_id}/applications")
async def list_applications(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="只能查看自己课程的申请")

    enrollments = await db.execute(
        select(CourseEnrollment)
        .where(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.status == "pending",
        )
        .order_by(CourseEnrollment.enrolled_at.desc())
    )
    rows = enrollments.scalars().all()

    result_list = []
    for e in rows:
        stu = await db.execute(select(User).where(User.id == e.student_id))
        student = stu.scalar_one_or_none()
        result_list.append({
            "id": e.id,
            "student_id": e.student_id,
            "student_name": student.display_name if student else "未知",
            "student_username": student.username if student else "未知",
            "applied_at": e.enrolled_at.isoformat() if e.enrolled_at else None,
        })

    return result_list


@router.post("/{course_id}/applications/{enrollment_id}/approve")
async def approve_application(
    course_id: int,
    enrollment_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="只能审批自己课程的申请")

    enrollment = await db.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.id == enrollment_id,
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.status == "pending",
        )
    )
    e = enrollment.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="申请不存在或已处理")

    e.status = "approved"
    await db.commit()
    return {"message": "已批准入班"}


@router.post("/{course_id}/applications/{enrollment_id}/reject")
async def reject_application(
    course_id: int,
    enrollment_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="只能审批自己课程的申请")

    enrollment = await db.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.id == enrollment_id,
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.status == "pending",
        )
    )
    e = enrollment.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="申请不存在或已处理")

    e.status = "rejected"
    await db.commit()
    return {"message": "已拒绝入班"}
