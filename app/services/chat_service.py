import json
import random
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course
from app.models.conversation import Conversation
from app.services.llm import chat_completion_stream, chat_completion
from app.services.rag import search

STUDENT_KEYS = ["basic", "medium", "advanced", "senior"]
STUDENT_NAMES = {"basic": "基础小问", "medium": "中坚小固", "advanced": "拓思考", "senior": "学长知喻"}
STUDENT_COLORS = {"basic": "#4CAF50", "medium": "#2196F3", "advanced": "#9C27B0", "senior": "#FF9800"}

TEACHER_SYSTEM_PROMPT_TEMPLATE = """你是一个AI教师，以下是你的角色设定：
{role_card}

教学原则：
1. 基于课程知识库内容回答，不编造事实
2. 对不清楚的内容要明确说明"这部分内容我不确定"
3. 回答要清晰、有条理，适当使用分点、举例
4. 鼓励学生思考和提问

以下是检索到的相关课程知识内容：
{knowledge_context}

对话历史摘要（最近的对话）：
{history_summary}

请根据以上内容回答学生的问题。"""

STUDENT_SYSTEM_PROMPT_TEMPLATE = """你是一个AI学生，以下是你的角色设定：
{role_card}

当前对话：
{conversation_context}

请以你的角色身份，根据对话内容做出简短回应（1-2句话）。
回应要符合你的角色设定和性格特点。
如果觉得没必要发言，可以说"skip"。"""


async def _get_course(course_id: int, db: AsyncSession) -> Course:
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise ValueError("课程不存在")
    return course


async def _build_history_summary(course_id: int, db: AsyncSession, limit: int = 10) -> str:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.course_id == course_id)
        .order_by(Conversation.created_at.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    messages.reverse()
    if not messages:
        return "暂无历史对话"

    lines = []
    for m in messages:
        speaker = m.speaker_type
        if speaker == "student":
            name = "学生"
        elif speaker == "ai_teacher":
            name = "AI教师"
        elif speaker == "ai_student":
            name = STUDENT_NAMES.get(str(m.speaker_id), f"AI学生({m.speaker_id})")
        else:
            name = speaker
        lines.append(f"{name}: {m.content[:200]}")
    return "\n".join(lines)


async def process_student_message(
    course_id: int,
    student_id: int,
    message: str,
    db: AsyncSession,
) -> str:
    course = await _get_course(course_id, db)

    user_msg = Conversation(
        course_id=course_id,
        speaker_type="student",
        speaker_id=student_id,
        content=message,
        created_at=datetime.utcnow(),
    )
    db.add(user_msg)

    teacher_card = json.loads(course.teacher_role_card) if course.teacher_role_card else {}

    rag_results = await search(course_id, message, top_k=5)
    knowledge_context = "\n\n".join(
        [f"[相关度 {r.get('relevance_score', 0):.2f}]: {r['text'][:500]}" for r in rag_results]
    ) if rag_results else "未检索到相关知识"

    history_summary = await _build_history_summary(course_id, db)

    system_prompt = TEACHER_SYSTEM_PROMPT_TEMPLATE.format(
        role_card=json.dumps(teacher_card, ensure_ascii=False, indent=2),
        knowledge_context=knowledge_context,
        history_summary=history_summary,
    )

    full_reply = await chat_completion(
        messages=[{"role": "user", "content": message}],
        system_prompt=system_prompt,
        temperature=0.7,
    )

    teacher_msg = Conversation(
        course_id=course_id,
        speaker_type="ai_teacher",
        speaker_id=0,
        content=full_reply,
        created_at=datetime.utcnow(),
    )
    db.add(teacher_msg)

    config = json.loads(course.student_roles_config) if course.student_roles_config else {}
    speech_rules = config.get("speech_rules", {})
    enabled = config.get("enabled", {s: True for s in STUDENT_KEYS})
    roles = config.get("roles", {})

    ai_student_reply = None
    for sk in STUDENT_KEYS:
        if not enabled.get(sk, True):
            continue
        rule = speech_rules.get(sk, {})
        activity_level = rule.get("activity_level", 0.5)
        trigger_mode = rule.get("trigger_mode", "keyword")
        keywords = rule.get("keywords", [])

        should_respond = False
        if trigger_mode == "always":
            should_respond = True
        elif trigger_mode == "keyword" and keywords:
            if any(kw in message for kw in keywords):
                should_respond = True
        elif trigger_mode == "mixed":
            if any(kw in message for kw in keywords) or random.random() < activity_level:
                should_respond = True
        elif trigger_mode == "round_robin":
            if random.random() < activity_level:
                should_respond = True

        if not should_respond:
            continue

        role_card = roles.get(sk, {})
        conversation_context = f"学生提问：{message}\nAI教师回答：{full_reply[:300]}"

        student_prompt = STUDENT_SYSTEM_PROMPT_TEMPLATE.format(
            role_card=json.dumps(role_card, ensure_ascii=False, indent=2),
            conversation_context=conversation_context,
        )

        student_reply = await chat_completion(
            messages=[{"role": "user", "content": f"请以{STUDENT_NAMES.get(sk, sk)}的身份回应"}],
            system_prompt=student_prompt,
            temperature=0.8,
            max_tokens=256,
        )

        if student_reply.strip().lower() == "skip":
            continue

        ai_msg = Conversation(
            course_id=course_id,
            speaker_type="ai_student",
            speaker_id=sk,
            content=student_reply,
            created_at=datetime.utcnow(),
        )
        db.add(ai_msg)
        ai_student_reply = {"type": sk, "name": STUDENT_NAMES.get(sk, sk), "content": student_reply}
        break

    await db.commit()
    return json.dumps({
        "teacher_reply": full_reply,
        "ai_student_reply": ai_student_reply,
    }, ensure_ascii=False)


async def stream_teacher_response(
    course_id: int,
    student_id: int,
    message: str,
    db: AsyncSession,
):
    yield f"data: {json.dumps({'type': 'status', 'message': '正在检索知识库...'})}\n\n"

    course = await _get_course(course_id, db)

    user_msg = Conversation(
        course_id=course_id,
        speaker_type="student",
        speaker_id=student_id,
        content=message,
        created_at=datetime.utcnow(),
    )
    db.add(user_msg)

    teacher_card = json.loads(course.teacher_role_card) if course.teacher_role_card else {}

    yield f"data: {json.dumps({'type': 'status', 'message': '正在分析问题...'})}\n\n"

    rag_results = await search(course_id, message, top_k=5)
    knowledge_context = "\n\n".join(
        [f"[相关度 {r.get('relevance_score', 0):.2f}]: {r['text'][:500]}" for r in rag_results]
    ) if rag_results else "未检索到相关知识"

    history_summary = await _build_history_summary(course_id, db)

    system_prompt = TEACHER_SYSTEM_PROMPT_TEMPLATE.format(
        role_card=json.dumps(teacher_card, ensure_ascii=False, indent=2),
        knowledge_context=knowledge_context,
        history_summary=history_summary,
    )

    yield f"data: {json.dumps({'type': 'status', 'message': 'AI教师正在输入...'})}\n\n"

    full_reply = ""
    async for chunk in chat_completion_stream(
        messages=[{"role": "user", "content": message}],
        system_prompt=system_prompt,
        temperature=0.7,
    ):
        full_reply += chunk
        yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"

    teacher_msg = Conversation(
        course_id=course_id,
        speaker_type="ai_teacher",
        speaker_id=0,
        content=full_reply,
        created_at=datetime.utcnow(),
    )
    db.add(teacher_msg)

    config = json.loads(course.student_roles_config) if course.student_roles_config else {}
    speech_rules = config.get("speech_rules", {})
    enabled = config.get("enabled", {s: True for s in STUDENT_KEYS})
    roles = config.get("roles", {})

    for sk in STUDENT_KEYS:
        if not enabled.get(sk, True):
            continue
        rule = speech_rules.get(sk, {})
        activity_level = rule.get("activity_level", 0.5)
        trigger_mode = rule.get("trigger_mode", "keyword")
        keywords = rule.get("keywords", [])

        should_respond = False
        if trigger_mode == "always":
            should_respond = True
        elif trigger_mode == "keyword" and keywords:
            if any(kw in message for kw in keywords):
                should_respond = True
        elif trigger_mode == "mixed":
            if any(kw in message for kw in keywords) or random.random() < activity_level:
                should_respond = True
        elif trigger_mode == "round_robin":
            if random.random() < activity_level:
                should_respond = True

        if not should_respond:
            continue

        role_card = roles.get(sk, {})
        conversation_context = f"学生提问：{message}\nAI教师回答：{full_reply[:300]}"

        student_prompt = STUDENT_SYSTEM_PROMPT_TEMPLATE.format(
            role_card=json.dumps(role_card, ensure_ascii=False, indent=2),
            conversation_context=conversation_context,
        )

        yield f"data: {json.dumps({'type': 'student_typing', 'student_type': sk, 'student_name': STUDENT_NAMES.get(sk, sk)})}\n\n"

        student_reply = await chat_completion(
            messages=[{"role": "user", "content": f"请以{STUDENT_NAMES.get(sk, sk)}的身份回应"}],
            system_prompt=student_prompt,
            temperature=0.8,
            max_tokens=256,
        )

        if student_reply.strip().lower() == "skip":
            continue

        ai_msg = Conversation(
            course_id=course_id,
            speaker_type="ai_student",
            speaker_id=sk,
            content=student_reply,
            created_at=datetime.utcnow(),
        )
        db.add(ai_msg)

        yield f"data: {json.dumps({'type': 'student_token', 'student_type': sk, 'student_name': STUDENT_NAMES.get(sk, sk), 'content': student_reply})}\n\n"
        break

    await db.commit()
    yield "data: [DONE]\n\n"
