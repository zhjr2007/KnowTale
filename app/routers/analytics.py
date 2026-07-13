from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.course import Course, CourseEnrollment
from app.models.conversation import Conversation
from app.models.quiz import Quiz, Question, QuizAttempt, Answer
from app.models.user import User
from app.models.notification import Notification
from app.dependencies import require_user, require_teacher
from app.services.analytics import analyze_conversations, generate_report, get_latest_report, get_knowledge_radar, get_low_participation_students
from app.services.role_updater import update_student_roles
from app.services.llm import chat_completion

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

    data = await generate_report(course_id, db=db)
    data["course_name"] = course.name

    db.add(Notification(
        user_id=course.teacher_id,
        type="weekly_report",
        title="\u5b66\u60c5\u5468\u62a5\u5df2\u751f\u6210",
        content=f"\u8bfe\u7a0b\u300c{course.name}\u300d\u7684\u5b66\u60c5\u5468\u62a5\u5df2\u751f\u6210\uff0c\u8bf7\u67e5\u770b",
        course_id=course_id,
    ))
    await db.commit()

    return data


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


@router.get("/{course_id}/student/{student_id}")
async def get_student_analytics(
    course_id: int,
    student_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    if user.role != "teacher" and user.id != student_id:
        raise HTTPException(status_code=403, detail="无权限查看其他学生报告")

    student_result = await db.execute(select(User).where(User.id == student_id))
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    cutoff = datetime.utcnow() - timedelta(days=30)
    conv_result = await db.execute(
        select(Conversation)
        .where(
            Conversation.course_id == course_id,
            Conversation.speaker_id == student_id,
            Conversation.speaker_type == "student",
            Conversation.created_at >= cutoff,
        )
        .order_by(Conversation.created_at.asc())
    )
    conversations = conv_result.scalars().all()

    total_messages = len(conversations)
    active_days = len(set(c.created_at.strftime("%Y-%m-%d") for c in conversations))
    last_active = conversations[-1].created_at if conversations else None

    quiz_ids_result = await db.execute(
        select(Quiz.id).where(Quiz.course_id == course_id)
    )
    quiz_ids = [row[0] for row in quiz_ids_result.all()]

    total_attempts = 0
    avg_score = 0
    weak_points = []
    if quiz_ids:
        a_result = await db.execute(
            select(
                func.count(QuizAttempt.id),
                func.avg(QuizAttempt.score * 1.0 / func.nullif(QuizAttempt.total, 0) * 100),
            )
            .where(
                QuizAttempt.student_id == student_id,
                QuizAttempt.quiz_id.in_(quiz_ids),
            )
        )
        row = a_result.one()
        total_attempts = row[0] or 0
        avg_score = round(row[1] or 0, 1)

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
            acc = round(k_correct / k_total * 100, 1) if k_total else 0
            if acc < 60:
                weak_points.append({"point": kp, "accuracy": acc})

    knowledge_radar = await get_knowledge_radar(course_id, student_id, db)

    weekly_trend = {}
    for c in conversations:
        iso = c.created_at.strftime("%Y-W%W")
        if iso not in weekly_trend:
            weekly_trend[iso] = {"msg_count": 0, "quiz_avg": 0}
        weekly_trend[iso]["msg_count"] += 1

    trend_data = [
        {"week": w, "msg_count": d["msg_count"], "quiz_avg": avg_score}
        for w, d in sorted(weekly_trend.items())
    ]

    recommendations = ""
    if total_messages > 0 or total_attempts > 0:
        prompt = f"""你是教学分析专家。以下是学生"{student.display_name}"在课程"{course.name}"中的学习数据：

参与情况：{total_messages} 条消息，{active_days} 个活跃日
答题情况：{total_attempts} 次练习，平均分 {avg_score}%
薄弱知识点：{', '.join(w['point'] for w in weak_points) if weak_points else '无明显薄弱点'}
知识点掌握度：{', '.join(f'{r["point"]}: {r["mastery"]}%' for r in knowledge_radar[:5])}

请给出个性化的学习建议（3-5条），用中文回答，简洁易懂。"""
        recommendations = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )

    return {
        "student_id": student_id,
        "student_name": student.display_name or student.username,
        "participation": {
            "total_messages": total_messages,
            "active_days": active_days,
            "last_active_at": last_active.isoformat() if last_active else None,
        },
        "quiz": {
            "total_attempts": total_attempts,
            "avg_score": avg_score,
            "weak_points": weak_points,
        },
        "knowledge_radar": knowledge_radar,
        "weekly_trend": trend_data,
        "recommendations": recommendations,
    }


@router.get("/{course_id}/export")
async def export_analytics(
    course_id: int,
    format: str = Query("html", pattern="^(html|json)$"),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    report = await get_latest_report(course_id, db=db)
    if not report:
        data = await analyze_conversations(course_id, days=7, db=db)
        report = data

    report["course_name"] = course.name

    if format == "json":
        return report

    from app.main import render_template
    return render_template(
        "analytics_export.html",
        request={},
        user=user,
        course_id=course_id,
        report=report,
    )


@router.get("/{course_id}/low-participation")
async def get_low_participation(
    course_id: int,
    threshold_days: int = Query(7, ge=1, le=30),
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    students = await get_low_participation_students(course_id, threshold_days=threshold_days, db=db)
    return {"course_id": course_id, "course_name": course.name, "students": students}
