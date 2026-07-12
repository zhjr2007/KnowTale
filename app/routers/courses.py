import random
import string
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models.course import Course, CourseEnrollment
from app.models.user import User
from app.dependencies import require_user, require_teacher
from app.services.agent_factory import (
    generate_teacher_role,
    generate_student_role,
    get_student_templates,
    get_default_speech_rules,
)

router = APIRouter(prefix="/api/courses", tags=["courses"])


def _generate_invite_code() -> str:
    return ''.join(random.choices(string.digits, k=6))


class CreateCourseRequest(BaseModel):
    name: str
    description: str = ""


class UpdateCourseRequest(BaseModel):
    name: str
    description: str = ""


@router.get("")
async def list_courses(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    status: str = Query("active", description="\u7b5b\u9009\u72b6\u6001: active/archived"),
):
    if user.role == "teacher":
        result = await db.execute(
            select(Course)
            .where(Course.teacher_id == user.id, Course.status == status)
            .order_by(Course.created_at.desc())
        )
        courses = result.scalars().all()
    else:
        result = await db.execute(
            select(Course).join(CourseEnrollment)
            .where(
                CourseEnrollment.student_id == user.id,
                CourseEnrollment.status == "approved",
                Course.status == "active",
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

        teacher_result = await db.execute(select(User).where(User.id == c.teacher_id))
        teacher = teacher_result.scalar_one_or_none()

        result_list.append({
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "teacher_id": c.teacher_id,
            "teacher_name": teacher.display_name if teacher else "\u672a\u77e5",
            "student_count": student_count,
            "status": c.status,
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


@router.put("/{course_id}")
async def update_course(
    course_id: int,
    req: UpdateCourseRequest,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="\u8bfe\u7a0b\u4e0d\u5b58\u5728")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="\u53ea\u80fd\u7f16\u8f91\u81ea\u5df1\u7684\u8bfe\u7a0b")

    course.name = req.name
    course.description = req.description
    await db.commit()
    await db.refresh(course)
    return {"id": course.id, "name": course.name, "description": course.description}


@router.delete("/{course_id}")
async def delete_course(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="\u8bfe\u7a0b\u4e0d\u5b58\u5728")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="\u53ea\u80fd\u5220\u9664\u81ea\u5df1\u7684\u8bfe\u7a0b")

    count_result = await db.execute(
        select(func.count(CourseEnrollment.id))
        .where(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.status == "approved",
        )
    )
    student_count = count_result.scalar() or 0
    if student_count > 0:
        raise HTTPException(status_code=400, detail="\u8bfe\u7a0b\u5df2\u6709\u5b66\u751f\u52a0\u5165\uff0c\u65e0\u6cd5\u5220\u9664")

    await db.delete(course)
    await db.commit()
    return {"message": "\u8bfe\u7a0b\u5df2\u5220\u9664"}


@router.post("/{course_id}/archive")
async def archive_course(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="\u8bfe\u7a0b\u4e0d\u5b58\u5728")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="\u53ea\u80fd\u5f52\u6863\u81ea\u5df1\u7684\u8bfe\u7a0b")

    course.status = "archived"
    await db.commit()
    return {"message": "\u8bfe\u7a0b\u5df2\u5f52\u6863"}


@router.post("/{course_id}/unarchive")
async def unarchive_course(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="\u8bfe\u7a0b\u4e0d\u5b58\u5728")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="\u53ea\u80fd\u6062\u590d\u81ea\u5df1\u7684\u8bfe\u7a0b")

    course.status = "active"
    await db.commit()
    return {"message": "\u8bfe\u7a0b\u5df2\u6062\u590d"}


@router.get("/{course_id}")
async def get_course(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="\u8bfe\u7a0b\u4e0d\u5b58\u5728")

    if user.role == "student":
        enrollment_result = await db.execute(
            select(CourseEnrollment).where(
                CourseEnrollment.course_id == course_id,
                CourseEnrollment.student_id == user.id,
                CourseEnrollment.status == "approved",
            )
        )
        if not enrollment_result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="\u672a\u52a0\u5165\u8be5\u8bfe\u7a0b")

    teacher_result = await db.execute(select(User).where(User.id == course.teacher_id))
    teacher = teacher_result.scalar_one_or_none()

    is_teacher = user.role == "teacher" and course.teacher_id == user.id

    return {
        "id": course.id,
        "name": course.name,
        "description": course.description,
        "teacher_name": teacher.display_name if teacher else "未知",
        "teacher_id": course.teacher_id,
        "status": course.status,
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
        raise HTTPException(status_code=403, detail="\u4ec5\u5b66\u751f\u53ef\u52a0\u5165\u8bfe\u7a0b")

    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="\u8bfe\u7a0b\u4e0d\u5b58\u5728")

    existing = await db.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.student_id == user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="\u5df2\u7533\u8bf7\u6216\u5df2\u52a0\u5165\u8be5\u8bfe\u7a0b")

    enrollment = CourseEnrollment(
        course_id=course_id,
        student_id=user.id,
        status="pending",
    )
    db.add(enrollment)
    await db.commit()

    return {"message": "\u5df2\u53d1\u9001\u5165\u73ed\u7533\u8bf7\uff0c\u7b49\u5f85\u8001\u5e08\u5ba1\u6279"}


@router.post("/join-by-invite")
async def join_course_by_invite(
    invite_code: str = Query(..., description="6\u4f4d\u9080\u8bf7\u7801"),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role != "student":
        raise HTTPException(status_code=403, detail="\u4ec5\u5b66\u751f\u53ef\u52a0\u5165\u8bfe\u7a0b")

    result = await db.execute(
        select(Course).where(Course.invite_code == invite_code, Course.status == "active")
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="\u9080\u8bf7\u7801\u65e0\u6548\u6216\u8bfe\u7a0b\u5df2\u5f52\u6863")

    existing = await db.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.course_id == course.id,
            CourseEnrollment.student_id == user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="\u5df2\u7533\u8bf7\u6216\u5df2\u52a0\u5165\u8be5\u8bfe\u7a0b")

    enrollment = CourseEnrollment(
        course_id=course.id,
        student_id=user.id,
        status="pending",
    )
    db.add(enrollment)
    await db.commit()

    return {"message": "\u5df2\u53d1\u9001\u5165\u73ed\u7533\u8bf7\uff0c\u7b49\u5f85\u8001\u5e08\u5ba1\u6279", "course_id": course.id, "course_name": course.name}


@router.get("/{course_id}/invite-code")
async def get_invite_code(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="\u8bfe\u7a0b\u4e0d\u5b58\u5728")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="\u53ea\u80fd\u67e5\u770b\u81ea\u5df1\u8bfe\u7a0b\u7684\u9080\u8bf7\u7801")

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
        raise HTTPException(status_code=404, detail="\u8bfe\u7a0b\u4e0d\u5b58\u5728")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="\u53ea\u80fd\u5237\u65b0\u81ea\u5df1\u8bfe\u7a0b\u7684\u9080\u8bf7\u7801")

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
        raise HTTPException(status_code=404, detail="\u8bfe\u7a0b\u4e0d\u5b58\u5728")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="\u53ea\u80fd\u67e5\u770b\u81ea\u5df1\u8bfe\u7a0b\u7684\u7533\u8bf7")

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
            "student_name": student.display_name if student else "\u672a\u77e5",
            "student_username": student.username if student else "\u672a\u77e5",
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
        raise HTTPException(status_code=404, detail="\u8bfe\u7a0b\u4e0d\u5b58\u5728")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="\u53ea\u80fd\u5ba1\u6279\u81ea\u5df1\u8bfe\u7a0b\u7684\u7533\u8bf7")

    enrollment = await db.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.id == enrollment_id,
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.status == "pending",
        )
    )
    e = enrollment.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="\u7533\u8bf7\u4e0d\u5b58\u5728\u6216\u5df2\u5904\u7406")

    e.status = "approved"
    await db.commit()
    return {"message": "\u5df2\u6279\u51c6\u5165\u73ed"}


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
        raise HTTPException(status_code=404, detail="\u8bfe\u7a0b\u4e0d\u5b58\u5728")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="\u53ea\u80fd\u5ba1\u6279\u81ea\u5df1\u8bfe\u7a0b\u7684\u7533\u8bf7")

    enrollment = await db.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.id == enrollment_id,
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.status == "pending",
        )
    )
    e = enrollment.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="\u7533\u8bf7\u4e0d\u5b58\u5728\u6216\u5df2\u5904\u7406")

    e.status = "rejected"
    await db.commit()
    return {"message": "\u5df2\u62d2\u7edd\u5165\u73ed"}


@router.post("/{course_id}/generate-teacher")
async def generate_teacher(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="\u8bfe\u7a0b\u4e0d\u5b58\u5728")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="\u53ea\u80fd\u64cd\u4f5c\u81ea\u5df1\u7684\u8bfe\u7a0b")

    teacher_card = await generate_teacher_role(
        course_name=course.name,
        course_description=course.description or "",
    )
    course.teacher_role_card = json.dumps(teacher_card, ensure_ascii=False)
    await db.commit()
    return teacher_card


@router.post("/{course_id}/generate-students")
async def generate_students(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="\u8bfe\u7a0b\u4e0d\u5b58\u5728")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="\u53ea\u80fd\u64cd\u4f5c\u81ea\u5df1\u7684\u8bfe\u7a0b")

    student_types = ["basic", "medium", "advanced", "senior"]
    roles = {}
    for stype in student_types:
        role = await generate_student_role(
            student_type=stype,
            course_name=course.name,
            course_description=course.description or "",
        )
        roles[stype] = role

    speech_rules = get_default_speech_rules()
    config = {
        "roles": roles,
        "speech_rules": speech_rules,
        "enabled": {t: True for t in student_types},
    }
    course.student_roles_config = json.dumps(config, ensure_ascii=False)
    await db.commit()
    return config


@router.get("/{course_id}/roles")
async def get_roles(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="\u8bfe\u7a0b\u4e0d\u5b58\u5728")

    teacher_card = json.loads(course.teacher_role_card) if course.teacher_role_card else None
    student_config = json.loads(course.student_roles_config) if course.student_roles_config else None

    templates_info = get_student_templates()

    return {
        "teacher_role_card": teacher_card,
        "student_roles_config": student_config,
        "student_templates": templates_info,
    }


class RoleSettingsRequest(BaseModel):
    enabled: bool | None = None
    activity_level: float | None = None
    trigger_mode: Literal["round_robin", "at", "keyword", "mixed"] | None = None
    keywords: list[str] | None = None
    min_interval: int | None = None


@router.put("/{course_id}/roles/{role_type}/settings")
async def update_role_settings(
    course_id: int,
    role_type: str,
    req: RoleSettingsRequest,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    valid_types = {"teacher", "basic", "medium", "advanced", "senior"}
    if role_type not in valid_types:
        raise HTTPException(status_code=400, detail="\u65e0\u6548\u7684\u89d2\u8272\u7c7b\u578b")

    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="\u8bfe\u7a0b\u4e0d\u5b58\u5728")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="\u53ea\u80fd\u64cd\u4f5c\u81ea\u5df1\u7684\u8bfe\u7a0b")

    if role_type == "teacher":
        if req.enabled is not None:
            teacher_card = json.loads(course.teacher_role_card) if course.teacher_role_card else {}
            teacher_card["enabled"] = req.enabled
            course.teacher_role_card = json.dumps(teacher_card, ensure_ascii=False)
        await db.commit()
        return {"message": "\u6559\u5e08\u89d2\u8272\u8bbe\u7f6e\u5df2\u66f4\u65b0"}
    else:
        student_config = json.loads(course.student_roles_config) if course.student_roles_config else {}
        if "speech_rules" not in student_config:
            student_config["speech_rules"] = json.loads(get_default_speech_rules())
        if "enabled" not in student_config:
            student_config["enabled"] = {}

        if req.enabled is not None:
            student_config.setdefault("enabled", {})[role_type] = req.enabled

        if role_type in student_config["speech_rules"]:
            rule = student_config["speech_rules"][role_type]
            if req.activity_level is not None:
                rule["activity_level"] = max(0.0, min(1.0, req.activity_level))
            if req.trigger_mode is not None:
                rule["trigger_mode"] = req.trigger_mode
            if req.keywords is not None:
                rule["keywords"] = req.keywords
            if req.min_interval is not None:
                rule["min_interval"] = max(1, req.min_interval)

        course.student_roles_config = json.dumps(student_config, ensure_ascii=False)
        await db.commit()
        return {"message": f"{role_type} \u89d2\u8272\u8bbe\u7f6e\u5df2\u66f4\u65b0"}
