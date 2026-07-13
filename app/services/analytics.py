import json
from datetime import datetime, timedelta, date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.conversation import Conversation, WeeklyReport
from app.models.quiz import Question, Answer, QuizAttempt, Quiz
from app.models.user import User
from app.models.course import CourseEnrollment
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
    speaker_type_count = {}
    daily_counts = {}
    ai_count = 0
    student_ids = set()
    student_msg_count = {}

    for c in conversations:
        if c.knowledge_tag:
            knowledge_tags[c.knowledge_tag] = knowledge_tags.get(c.knowledge_tag, 0) + 1
        speaker_type_count[c.speaker_type] = speaker_type_count.get(c.speaker_type, 0) + 1
        day_key = c.created_at.strftime("%Y-%m-%d")
        daily_counts[day_key] = daily_counts.get(day_key, 0) + 1
        if c.speaker_type in ("ai_teacher", "ai_student"):
            ai_count += 1
        if c.speaker_type == "student":
            student_ids.add(c.speaker_id)
            sid = c.speaker_id
            if sid not in student_msg_count:
                student_msg_count[sid] = {"count": 0, "last_active": c.created_at}
            student_msg_count[sid]["count"] += 1
            if c.created_at > student_msg_count[sid]["last_active"]:
                student_msg_count[sid]["last_active"] = c.created_at

    top10 = sorted(knowledge_tags.items(), key=lambda x: x[1], reverse=True)[:10]
    student_count = len(student_ids)
    ai_ratio = round(ai_count / total_messages * 100, 1) if total_messages else 0
    weak_tags = [tag for tag, cnt in knowledge_tags.items() if cnt <= 1]

    trend = sorted([{"date": d, "count": c} for d, c in daily_counts.items()], key=lambda x: x["date"])

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
        "trend": trend,
        "participation_distribution": speaker_type_count,
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


async def get_knowledge_radar(
    course_id: int,
    student_id: int,
    db: AsyncSession,
) -> list[dict]:
    quiz_ids_result = await db.execute(
        select(Quiz.id).where(Quiz.course_id == course_id)
    )
    quiz_ids = [row[0] for row in quiz_ids_result.all()]

    mastery = {}

    if quiz_ids:
        k_result = await db.execute(
            select(
                Question.knowledge_point,
                func.count(Answer.id),
                func.sum(Answer.is_correct),
            )
            .select_from(Answer)
            .join(Question, Answer.question_id == Question.id)
            .join(QuizAttempt, Answer.attempt_id == QuizAttempt.id)
            .where(
                QuizAttempt.student_id == student_id,
                Question.quiz_id.in_(quiz_ids),
            )
            .group_by(Question.knowledge_point)
        )
        for row in k_result:
            kp = row[0] or "未分类"
            k_total = row[1] or 0
            k_correct = row[2] or 0
            if k_total > 0:
                mastery[kp] = mastery.get(kp, 0) + (k_correct / k_total) * 70

    conv_result = await db.execute(
        select(Conversation.knowledge_tag, func.count(Conversation.id))
        .where(
            Conversation.course_id == course_id,
            Conversation.speaker_id == student_id,
            Conversation.knowledge_tag.isnot(None),
        )
        .group_by(Conversation.knowledge_tag)
    )
    conv_total = 0
    conv_counts = {}
    for row in conv_result:
        tag = row[0] or "未分类"
        cnt = row[1] or 0
        conv_counts[tag] = cnt
        conv_total += cnt

    for tag, cnt in conv_counts.items():
        if conv_total > 0:
            mastery[tag] = mastery.get(tag, 0) + (cnt / conv_total) * 30

    return [{"point": k, "mastery": round(min(v, 100), 1)} for k, v in sorted(mastery.items(), key=lambda x: x[1], reverse=True)]


async def get_low_participation_students(
    course_id: int,
    threshold_days: int = 7,
    db: AsyncSession | None = None,
) -> list[dict]:
    close_db = db is None
    if db is None:
        async with async_session() as db:
            return await get_low_participation_students(course_id, threshold_days=threshold_days, db=db)

    cutoff = datetime.utcnow() - timedelta(days=threshold_days)

    enrollment_result = await db.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.status == "approved",
        )
    )
    enrolled = enrollment_result.scalars().all()
    if not enrolled:
        return []

    student_ids = [e.student_id for e in enrolled]
    user_result = await db.execute(
        select(User).where(User.id.in_(student_ids))
    )
    users = {u.id: u for u in user_result.scalars().all()}

    conv_result = await db.execute(
        select(
            Conversation.speaker_id,
            func.count(Conversation.id),
            func.max(Conversation.created_at),
        )
        .where(
            Conversation.course_id == course_id,
            Conversation.speaker_type == "student",
            Conversation.created_at >= cutoff,
        )
        .group_by(Conversation.speaker_id)
    )
    student_activity = {}
    for row in conv_result:
        sid = row[0]
        msg_count = row[1] or 0
        last_active = row[2]
        student_activity[sid] = {"msg_count": msg_count, "last_active": last_active}

    quiz_ids_result = await db.execute(
        select(Quiz.id).where(Quiz.course_id == course_id)
    )
    quiz_ids = [row[0] for row in quiz_ids_result.all()]

    student_quiz_counts = {}
    if quiz_ids:
        quiz_result = await db.execute(
            select(
                QuizAttempt.student_id,
                func.count(QuizAttempt.id),
            )
            .where(
                QuizAttempt.student_id.in_(student_ids),
                QuizAttempt.quiz_id.in_(quiz_ids),
                QuizAttempt.completed_at >= cutoff,
            )
            .group_by(QuizAttempt.student_id)
        )
        for row in quiz_result:
            student_quiz_counts[row[0]] = row[1] or 0

    low_participation = []
    for sid in student_ids:
        user = users.get(sid)
        if not user:
            continue
        activity = student_activity.get(sid, {"msg_count": 0, "last_active": None})
        quiz_count = student_quiz_counts.get(sid, 0)
        if activity["msg_count"] < 3 or quiz_count == 0:
            low_participation.append({
                "id": sid,
                "username": user.username,
                "display_name": user.display_name or user.username,
                "avatar": user.avatar,
                "last_active_at": activity["last_active"].isoformat() if activity["last_active"] else None,
                "message_count_7d": activity["msg_count"],
                "quiz_count_7d": quiz_count,
            })

    return low_participation


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
