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
    status: str = Query("active", description="筛选状态: active/archived"),
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
            "teacher_name": teacher.display_name if teacher else "未知",
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
        raise HTTPException(status_code=404, detail="课程不存在")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="只能编辑自己的课程")

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
        raise HTTPException(status_code=404, detail="课程不存在")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="只能删除自己的课程")

    count_result = await db.execute(
        select(func.count(CourseEnrollment.id))
        .where(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.status == "approved",
        )
    )
    student_count = count_result.scalar() or 0
    if student_count > 0:
        raise HTTPException(status_code=400, detail="课程已有学生加入，无法删除")

    await db.delete(course)
    await db.commit()
    return {"message": "课程已删除"}


@router.post("/{course_id}/archive")
async def archive_course(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="只能归档自己的课程")

    course.status = "archived"
    await db.commit()
    return {"message": "课程已归档"}


@router.post("/{course_id}/unarchive")
async def unarchive_course(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="只能恢复自己的课程")

    course.status = "active"
    await db.commit()
    return {"message": "课程已恢复"}


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
        select(Course).where(Course.invite_code == invite_code, Course.status == "active")
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="邀请码无效或课程已归档")

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


@router.post("/{course_id}/generate-teacher")
async def generate_teacher(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="只能操作自己的课程")

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
        raise HTTPException(status_code=404, detail="课程不存在")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="只能操作自己的课程")

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
        raise HTTPException(status_code=404, detail="课程不存在")

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
        raise HTTPException(status_code=400, detail="无效的角色类型")

    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    if course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="只能操作自己的课程")

    if role_type == "teacher":
        if req.enabled is not None:
            teacher_card = json.loads(course.teacher_role_card) if course.teacher_role_card else {}
            teacher_card["enabled"] = req.enabled
            course.teacher_role_card = json.dumps(teacher_card, ensure_ascii=False)
        await db.commit()
        return {"message": "教师角色设置已更新"}
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
        return {"message": f"{role_type} 角色设置已更新"}
