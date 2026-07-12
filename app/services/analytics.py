import json
from datetime import datetime, timedelta, date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.conversation import Conversation, WeeklyReport
from app.services.llm import chat_completion


async def analyze_conversations(
    course_id: int,
    days: int = 7,
    db: AsyncSession | None = None,
) -> dict:
    close_db = db is None
    if db is None:
        async with async_session() as db:
            return await analyze_conversations(course_id, days=days, db=db)

    cutoff = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.course_id == course_id,
            Conversation.created_at >= cutoff,
        )
        .order_by(Conversation.created_at.asc())
    )
    conversations = result.scalars().all()

    total_messages = len(conversations)

    knowledge_tags = {}
    ai_count = 0
    student_ids = set()

    for c in conversations:
        if c.knowledge_tag:
            knowledge_tags[c.knowledge_tag] = knowledge_tags.get(c.knowledge_tag, 0) + 1
        if c.speaker_type in ("ai_teacher", "ai_student"):
            ai_count += 1
        if c.speaker_type == "student":
            student_ids.add(c.speaker_id)

    top10 = sorted(knowledge_tags.items(), key=lambda x: x[1], reverse=True)[:10]
    student_count = len(student_ids)
    ai_ratio = round(ai_count / total_messages * 100, 1) if total_messages else 0
    all_tags = set(knowledge_tags.keys())
    weak_tags = [tag for tag, cnt in knowledge_tags.items() if cnt <= 1]

    weak_analysis = ""
    suggestion = ""
    if total_messages > 0 and top10:
        top10_text = "\n".join(f"- {tag}: {cnt}次" for tag, cnt in top10)
        weak_text = "、".join(weak_tags) if weak_tags else "无"
        prompt = f"""你是一位教学分析专家。以下是一个课程最近7天的课堂讨论数据：

总消息数：{total_messages}
高频问题 TOP10：
{top10_text}

出现较少的知识点标签：{weak_text}
AI发言占比：{ai_ratio}%
参与学生数：{student_count}

请分析：
1. 学生的薄弱知识点有哪些？
2. 给出具体的教学优化建议（3-5条）
3. 这些高频问题反映了什么学习规律？

请用中文回答，条理清晰。"""
        analysis_result = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )

        lines = analysis_result.strip().split("\n", 1)
        weak_analysis = lines[0] if len(lines) > 0 else analysis_result
        suggestion = lines[1] if len(lines) > 1 else ""

    return {
        "course_id": course_id,
        "total_messages": total_messages,
        "student_count": student_count,
        "ai_message_count": ai_count,
        "ai_message_ratio": ai_ratio,
        "top10": [{"tag": tag, "count": cnt} for tag, cnt in top10],
        "weak_tags": weak_tags,
        "weak_analysis": weak_analysis,
        "suggestion": suggestion,
        "analyzed_at": datetime.utcnow().isoformat(),
    }


async def generate_report(
    course_id: int,
    db: AsyncSession | None = None,
) -> dict:
    close_db = db is None
    if db is None:
        async with async_session() as db:
            return await generate_report(course_id, db=db)

    data = await analyze_conversations(course_id, days=7, db=db)

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    report = WeeklyReport(
        course_id=course_id,
        week_start=week_start,
        week_end=week_end,
        report_json=json.dumps(data, ensure_ascii=False),
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    data["report_id"] = report.id
    data["week_start"] = week_start.isoformat()
    data["week_end"] = week_end.isoformat()
    return data


async def get_latest_report(
    course_id: int,
    db: AsyncSession | None = None,
) -> dict | None:
    close_db = db is None
    if db is None:
        async with async_session() as db:
            return await get_latest_report(course_id, db=db)

    result = await db.execute(
        select(WeeklyReport)
        .where(WeeklyReport.course_id == course_id)
        .order_by(WeeklyReport.created_at.desc())
        .limit(1)
    )
    report = result.scalar_one_or_none()
    if not report:
        return None

    data = json.loads(report.report_json)
    data["report_id"] = report.id
    data["week_start"] = report.week_start.isoformat()
    data["week_end"] = report.week_end.isoformat()
    return data
