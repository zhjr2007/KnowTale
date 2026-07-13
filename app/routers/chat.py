import json
from typing import Optional

from fastapi import APIRouter, Depends, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_user
from app.models.user import User
from app.models.conversation import Conversation
from app.models.course import Course
from app.services.chat_service import process_student_message, stream_teacher_response, STUDENT_NAMES

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/send/{course_id}")
async def send_message(
    course_id: int,
    message: str = Form(...),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await process_student_message(course_id, user.id, message, db)
    data = json.loads(result)
    return data


@router.get("/stream/{course_id}")
async def stream_chat(
    course_id: int,
    message: str = Query(...),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return StreamingResponse(
        stream_teacher_response(course_id, user.id, message, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/history/{course_id}")
async def get_history(
    course_id: int,
    before_id: Optional[int] = Query(None),
    limit: int = Query(50, le=100),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Conversation).where(
        Conversation.course_id == course_id
    )

    if before_id:
        query = query.where(Conversation.id < before_id)

    query = query.order_by(Conversation.created_at.desc()).limit(limit)
    result = await db.execute(query)
    messages = result.scalars().all()
    messages.reverse()

    result_list = []
    for m in messages:
        speaker_name = ""
        if m.speaker_type == "student":
            student_result = await db.execute(select(User).where(User.id == m.speaker_id))
            student = student_result.scalar_one_or_none()
            speaker_name = student.display_name if student else "学生"
        elif m.speaker_type == "ai_teacher":
            speaker_name = "AI教师"
        elif m.speaker_type == "ai_student":
            speaker_name = STUDENT_NAMES.get(str(m.speaker_id), f"AI学生({m.speaker_id})")

        result_list.append({
            "id": m.id,
            "speaker_type": m.speaker_type,
            "speaker_id": m.speaker_id,
            "speaker_name": speaker_name,
            "content": m.content,
            "knowledge_tag": m.knowledge_tag,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })

    return result_list


@router.get("/participants/{course_id}")
async def get_participants(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        return {"participants": []}

    teacher_card = json.loads(course.teacher_role_card) if course.teacher_role_card else {}
    student_config = json.loads(course.student_roles_config) if course.student_roles_config else {}
    roles = student_config.get("roles", {})
    enabled = student_config.get("enabled", {})

    participants = [
        {
            "type": "ai_teacher",
            "id": 0,
            "name": teacher_card.get("name", "AI教师"),
            "color": "#FFD700",
        }
    ]

    student_types = {"basic": "基础小问", "medium": "中坚小固", "advanced": "拓思考", "senior": "学长知喻"}
    student_colors = {"basic": "#4CAF50", "medium": "#2196F3", "advanced": "#9C27B0", "senior": "#FF9800"}

    for sk, sname in student_types.items():
        if enabled.get(sk, True):
            role_data = roles.get(sk, {})
            participants.append({
                "type": "ai_student",
                "id": sk,
                "name": role_data.get("name", sname),
                "color": student_colors.get(sk, "#666"),
            })

    return {"participants": participants, "user_name": user.display_name or user.username}
