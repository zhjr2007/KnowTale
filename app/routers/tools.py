import json
import random
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_user
from app.models.user import User
from app.models.course import Course, CourseEnrollment
from app.models.quiz import Quiz, Question, QuizAttempt, Answer, WrongBookRecord
from app.models.notification import Notification
from app.models.study_plan import StudyPlan, StudyPlanItem
from app.services.quiz_generator import generate_quiz, grade_short_answer, generate_mindmap, generate_wrong_book_quiz
from app.services.rag import search

router = APIRouter(tags=["tools"])


# ─── 题库 ──────────────────────────────────────────────

@router.post("/api/quiz/generate/{course_id}")
async def create_quiz(
    course_id: int,
    body: dict,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="仅老师可生成练习")

    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    num = min(int(body.get("num_questions", 5)), 20)
    difficulty = body.get("difficulty", "mixed")
    focus = body.get("focus")

    questions_data = await generate_quiz(course_id, course.name, num, difficulty, focus)
    if not questions_data:
        raise HTTPException(status_code=400, detail="生成失败")

    quiz = Quiz(
        course_id=course_id,
        title=body.get("title", f"{course.name} 练习"),
        question_count=len(questions_data),
    )
    db.add(quiz)
    await db.flush()

    for q in questions_data:
        db.add(Question(
            quiz_id=quiz.id,
            content=q.get("content", ""),
            question_type=q.get("type", "short_answer"),
            options=json.dumps(q.get("options"), ensure_ascii=False) if q.get("options") else None,
            correct_answer=q.get("answer", ""),
            knowledge_point=q.get("knowledge_point", ""),
            difficulty=q.get("difficulty", "medium"),
        ))

    await db.commit()
    await db.refresh(quiz)

    enroll_result = await db.execute(
        select(CourseEnrollment).where(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.status == "approved",
        )
    )
    enrolled_students = enroll_result.scalars().all()
    for enrollment in enrolled_students:
        db.add(Notification(
            user_id=enrollment.student_id,
            type="quiz_published",
            title=f"\u65b0\u7ec3\u4e60\u53d1\u5e03\uff1a{quiz.title}",
            content=f"\u8bfe\u7a0b\u300c{course.name}\u300d\u65b0\u589e\u4e86\u4e00\u4efd\u7ec3\u4e60\uff0c\u8bf7\u53ca\u65f6\u5b8c\u6210",
            course_id=course_id,
        ))
    await db.commit()

    return {"id": quiz.id, "title": quiz.title, "question_count": quiz.question_count}


@router.get("/api/quiz/list/{course_id}")
async def list_quizzes(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Quiz).where(Quiz.course_id == course_id).order_by(Quiz.created_at.desc())
    )
    quizzes = result.scalars().all()

    quiz_ids = [q.id for q in quizzes]
    attempt_map = {}
    if quiz_ids:
        a_result = await db.execute(
            select(QuizAttempt)
            .where(
                QuizAttempt.quiz_id.in_(quiz_ids),
                QuizAttempt.student_id == user.id,
            )
            .order_by(QuizAttempt.completed_at.desc())
        )
        for a in a_result.scalars().all():
            if a.quiz_id not in attempt_map:
                attempt_map[a.quiz_id] = a

    return [
        {
            "id": q.id, "title": q.title,
            "question_count": q.question_count,
            "created_at": q.created_at.isoformat() if q.created_at else None,
            "attempt": {
                "score": attempt_map[q.id].score,
                "total": attempt_map[q.id].total,
                "percentage": round(attempt_map[q.id].score / attempt_map[q.id].total * 100, 1) if attempt_map[q.id].total else 0,
            } if q.id in attempt_map else None,
        }
        for q in quizzes
    ]


@router.get("/api/quiz/{quiz_id}")
async def get_quiz(
    quiz_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Quiz).where(Quiz.id == quiz_id))
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=404, detail="练习不存在")

    q_result = await db.execute(
        select(Question).where(Question.quiz_id == quiz_id)
    )
    questions = q_result.scalars().all()

    return {
        "id": quiz.id,
        "title": quiz.title,
        "question_count": quiz.question_count,
        "questions": [
            {
                "id": q.id,
                "content": q.content,
                "type": q.question_type,
                "options": json.loads(q.options) if q.options else None,
                "knowledge_point": q.knowledge_point,
                "difficulty": q.difficulty,
            }
            for q in questions
        ],
    }


@router.post("/api/quiz/{quiz_id}/submit")
async def submit_quiz(
    quiz_id: int,
    body: dict,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    quiz_result = await db.execute(select(Quiz).where(Quiz.id == quiz_id))
    quiz_obj = quiz_result.scalar_one_or_none()
    if not quiz_obj:
        raise HTTPException(status_code=404, detail="练习不存在")

    q_result = await db.execute(
        select(Question).where(Question.quiz_id == quiz_id)
    )
    questions = {q.id: q for q in q_result.scalars().all()}
    if not questions:
        raise HTTPException(status_code=404, detail="练习无题目")

    answers_data = body.get("answers", {})
    if isinstance(answers_data, list):
        answers_data = {a.get("question_id"): a.get("answer") for a in answers_data}

    attempt = QuizAttempt(
        quiz_id=quiz_id,
        student_id=user.id,
        total=len(questions),
    )
    db.add(attempt)
    await db.flush()

    score = 0
    wrong_records = []

    for qid, q in questions.items():
        student_ans = str(answers_data.get(str(qid), answers_data.get(qid, "")))

        if q.question_type == "choice":
            is_correct = 1 if student_ans.strip().upper() == q.correct_answer.strip().upper() else 0
            feedback = ""
        else:
            correct, feedback = await grade_short_answer(q.content, q.correct_answer, student_ans)
            is_correct = 1 if correct else 0

        if is_correct:
            score += 1
        else:
            wrong_records.append(WrongBookRecord(
                student_id=user.id,
                course_id=quiz_obj.course_id,
                question_content=q.content,
                correct_answer=q.correct_answer,
                student_answer=student_ans,
                knowledge_point=q.knowledge_point,
                question_type=q.question_type,
                source_quiz_id=quiz_id,
                next_review_date=date.today(),
            ))

        db.add(Answer(
            attempt_id=attempt.id,
            question_id=qid,
            student_answer=student_ans,
            is_correct=is_correct,
            feedback=feedback,
        ))

    attempt.score = score
    for rec in wrong_records:
        db.add(rec)
    await db.commit()

    return {
        "attempt_id": attempt.id,
        "score": score,
        "total": len(questions),
        "percentage": round(score / len(questions) * 100, 1),
    }


@router.get("/api/quiz/{quiz_id}/result/{attempt_id}")
async def get_result(
    quiz_id: int,
    attempt_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(QuizAttempt).where(
            QuizAttempt.id == attempt_id,
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.student_id == user.id,
        )
    )
    attempt = result.scalar_one_or_none()
    if not attempt:
        raise HTTPException(status_code=404, detail="记录不存在")

    a_result = await db.execute(
        select(Answer).where(Answer.attempt_id == attempt_id)
    )
    answers = a_result.scalars().all()

    return {
        "attempt_id": attempt.id,
        "score": attempt.score,
        "total": attempt.total,
        "percentage": round(attempt.score / attempt.total * 100, 1) if attempt.total else 0,
        "answers": [
            {
                "question_id": a.question_id,
                "student_answer": a.student_answer,
                "is_correct": a.is_correct,
                "feedback": a.feedback,
            }
            for a in answers
        ],
    }


# ─── 错题本 ────────────────────────────────────────────

@router.get("/api/wrong-book/{course_id}")
async def list_wrong_book(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WrongBookRecord)
        .where(
            WrongBookRecord.student_id == user.id,
            WrongBookRecord.course_id == course_id,
        )
        .order_by(WrongBookRecord.created_at.desc())
    )
    records = result.scalars().all()
    return [
        {
            "id": r.id,
            "question_content": r.question_content,
            "correct_answer": r.correct_answer,
            "student_answer": r.student_answer,
            "knowledge_point": r.knowledge_point,
            "question_type": r.question_type,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "review_count": r.review_count,
            "next_review_date": r.next_review_date.isoformat() if r.next_review_date else None,
            "last_review_at": r.last_review_at.isoformat() if r.last_review_at else None,
        }
        for r in records
    ]


@router.delete("/api/wrong-book/{record_id}")
async def delete_wrong_record(
    record_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WrongBookRecord).where(
            WrongBookRecord.id == record_id,
            WrongBookRecord.student_id == user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    await db.delete(record)
    await db.commit()
    return {"message": "已删除"}


# ─── 间隔重复复习 ──────────────────────────────────────

@router.get("/api/wrong-book/review-today/{course_id}")
async def get_todays_review(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """返回今天需要复习的错题"""
    result = await db.execute(
        select(WrongBookRecord)
        .where(
            WrongBookRecord.student_id == user.id,
            WrongBookRecord.course_id == course_id,
            WrongBookRecord.next_review_date <= date.today(),
        )
        .order_by(WrongBookRecord.next_review_date.asc())
        .limit(10)
    )
    records = result.scalars().all()
    return [
        {
            "id": r.id,
            "question_content": r.question_content,
            "correct_answer": r.correct_answer,
            "student_answer": r.student_answer,
            "knowledge_point": r.knowledge_point,
            "question_type": r.question_type,
            "review_count": r.review_count,
            "next_review_date": r.next_review_date.isoformat() if r.next_review_date else None,
        }
        for r in records
    ]


@router.post("/api/wrong-book/review/{record_id}")
async def review_wrong_record(
    record_id: int,
    is_correct: bool = Form(...),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """复习错题后更新间隔重复参数 (简化版 SM-2)"""
    result = await db.execute(
        select(WrongBookRecord).where(
            WrongBookRecord.id == record_id,
            WrongBookRecord.student_id == user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    if is_correct:
        record.review_count += 1
        interval = min(2 ** record.review_count, 30)
    else:
        record.review_count = 0
        interval = 1

    record.next_review_date = date.today() + timedelta(days=interval)
    record.last_review_at = datetime.utcnow()
    await db.commit()

    return {
        "id": record.id,
        "review_count": record.review_count,
        "next_review_date": record.next_review_date.isoformat() if record.next_review_date else None,
        "interval_days": interval,
    }


# ─── 错题巩固 ────────────────────────────────────────────

@router.post("/api/wrong-book/redo/{course_id}")
async def redo_wrong_book(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """基于错题本生成巩固练习"""
    result = await db.execute(
        select(WrongBookRecord)
        .where(
            WrongBookRecord.student_id == user.id,
            WrongBookRecord.course_id == course_id,
        )
        .order_by(WrongBookRecord.created_at.desc())
    )
    records = result.scalars().all()
    if not records:
        raise HTTPException(status_code=400, detail="错题本为空，无需巩固")

    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    records_data = [
        {"knowledge_point": r.knowledge_point or "", "question_content": r.question_content}
        for r in records
    ]
    questions_data = await generate_wrong_book_quiz(records_data, course.name)
    if not questions_data:
        raise HTTPException(status_code=400, detail="生成巩固练习失败")

    quiz = Quiz(
        course_id=course_id,
        title=f"{course.name} 错题巩固",
        question_count=len(questions_data),
    )
    db.add(quiz)
    await db.flush()

    for q in questions_data:
        db.add(Question(
            quiz_id=quiz.id,
            content=q.get("content", ""),
            question_type=q.get("type", "short_answer"),
            options=json.dumps(q.get("options"), ensure_ascii=False) if q.get("options") else None,
            correct_answer=q.get("answer", ""),
            knowledge_point=q.get("knowledge_point", ""),
            difficulty=q.get("difficulty", "medium"),
        ))

    await db.commit()
    await db.refresh(quiz)
    return {"id": quiz.id, "title": quiz.title, "question_count": quiz.question_count}


# ─── 抽背 ──────────────────────────────────────────────

@router.post("/api/review/start/{course_id}")
async def start_review(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    from app.services.rag import get_chunk_count
    count = await get_chunk_count(course_id)
    return {"course_id": course_id, "course_name": course.name, "chunks": count}


@router.get("/api/review/question/{course_id}")
async def get_review_question(
    course_id: int,
    skip: str = "",
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    used = [s.strip() for s in skip.split(",") if s.strip()]

    from app.services.quiz_generator import generate_review_question
    question = await generate_review_question(course_id, course.name, used)
    if not question:
        raise HTTPException(status_code=404, detail="题目生成失败")

    return {
        "question": question.get("question", ""),
        "knowledge_point": question.get("knowledge_point", ""),
        "answer_hidden": True,
    }


@router.post("/api/review/check")
async def check_review_answer(body: dict):
    question = body.get("question", "")
    correct = body.get("correct_answer", "")
    student_ans = body.get("student_answer", "")

    is_correct, feedback = await grade_short_answer(question, correct, student_ans)
    return {"is_correct": is_correct, "feedback": feedback, "correct_answer": correct}


PEER_PERSONAS = [
    {"name": "小明", "type": "勤奋型", "trait": "学习认真但偶尔理解偏差，答案大部分正确但不够精确"},
    {"name": "小红", "type": "粗心型", "trait": "基础不错但容易粗心，答案有时遗漏关键点"},
    {"name": "小华", "type": "学霸型", "trait": "理解透彻，答案准确完整，表达清晰"},
    {"name": "小莉", "type": "困惑型", "trait": "正在努力学习中，答案经常不完整或有偏差"},
]


async def _generate_peer_answer(question: str, persona: dict, course_name: str) -> str:
    from app.services.llm import chat_completion
    prompt = f"""你是一位{persona['type']}学生{persona['name']}。
特点：{persona['trait']}

课程：{course_name}
请回答以下问题。回答要符合你的学生角色特点，不要过于完美也不要过于离谱。

问题：{question}"""
    answer = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        system_prompt="你正在模拟一个真实的学生角色。请用第一人称回答，语气自然。",
        temperature=0.8,
        max_tokens=512,
    )
    return answer.strip()


@router.post("/api/review/peer/{course_id}")
async def start_peer_review(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """启动 AI 学生陪练模式"""
    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    persona = random.choice(PEER_PERSONAS)
    from app.services.quiz_generator import generate_review_question
    question = await generate_review_question(course_id, course.name, [])
    if not question:
        raise HTTPException(status_code=404, detail="题目生成失败")

    peer_answer = await _generate_peer_answer(
        question.get("question", ""), persona, course.name
    )

    return {
        "course_id": course_id,
        "course_name": course.name,
        "persona": persona,
        "question": question.get("question", ""),
        "knowledge_point": question.get("knowledge_point", ""),
        "correct_answer": question.get("answer", ""),
        "peer_answer": peer_answer,
    }


@router.get("/api/review/peer/question/{course_id}")
async def get_peer_question(
    course_id: int,
    skip: str = "",
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """获取下一道 AI 陪练题"""
    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    used = [s.strip() for s in skip.split(",") if s.strip()]
    from app.services.quiz_generator import generate_review_question
    question = await generate_review_question(course_id, course.name, used)
    if not question:
        raise HTTPException(status_code=404, detail="题目生成失败")

    persona = random.choice(PEER_PERSONAS)
    peer_answer = await _generate_peer_answer(
        question.get("question", ""), persona, course.name
    )

    return {
        "persona": persona,
        "question": question.get("question", ""),
        "knowledge_point": question.get("knowledge_point", ""),
        "correct_answer": question.get("answer", ""),
        "peer_answer": peer_answer,
    }


# ─── 练习统计 ─

@router.get("/api/quiz/stats/{course_id}")
async def quiz_stats(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """增强版练习统计 - 区分学生和教师视角"""
    quiz_ids_result = await db.execute(
        select(Quiz.id).where(Quiz.course_id == course_id)
    )
    quiz_ids = [row[0] for row in quiz_ids_result.all()]
    if not quiz_ids:
        return {
            "by_knowledge_point": [], "by_difficulty": [],
            "weekly_trend": [], "total_quizzes": 0,
            "total_attempts": 0, "overall_percentage": 0,
            "weakest_points": [],
        }

    if user.role == "teacher":
        student_ids_result = await db.execute(
            select(CourseEnrollment.student_id).where(
                CourseEnrollment.course_id == course_id,
                CourseEnrollment.status == "approved",
            )
        )
        student_ids = [row[0] for row in student_ids_result.all()]
        if not student_ids:
            return {
                "by_knowledge_point": [], "by_difficulty": [],
                "weekly_trend": [], "total_quizzes": 0,
                "total_attempts": 0, "overall_percentage": 0,
                "weakest_points": [],
            }
        attempt_filter = QuizAttempt.student_id.in_(student_ids)
    else:
        attempt_filter = QuizAttempt.student_id == user.id

    a_result = await db.execute(
        select(func.count(QuizAttempt.id), func.sum(QuizAttempt.score), func.sum(QuizAttempt.total))
        .where(attempt_filter, QuizAttempt.quiz_id.in_(quiz_ids))
    )
    row = a_result.one()
    total_attempts = row[0] or 0
    total_correct = row[1] or 0
    total_questions = row[2] or 0
    overall_percentage = round(total_correct / total_questions * 100, 1) if total_questions else 0

    k_result = await db.execute(
        select(
            Question.knowledge_point,
            func.count(Answer.id),
            func.sum(Answer.is_correct),
        )
        .select_from(Answer)
        .join(Question, Answer.question_id == Question.id)
        .join(QuizAttempt, Answer.attempt_id == QuizAttempt.id)
        .where(attempt_filter, Question.quiz_id.in_(quiz_ids))
        .group_by(Question.knowledge_point)
    )
    by_knowledge_point = []
    for row in k_result:
        kp = row[0] or "未分类"
        k_total = row[1] or 0
        k_correct = row[2] or 0
        by_knowledge_point.append({
            "name": kp,
            "total": k_total,
            "correct": k_correct,
            "percentage": round(k_correct / k_total * 100, 1) if k_total else 0,
        })

    d_result = await db.execute(
        select(
            Question.difficulty,
            func.count(Answer.id),
            func.sum(Answer.is_correct),
        )
        .select_from(Answer)
        .join(Question, Answer.question_id == Question.id)
        .join(QuizAttempt, Answer.attempt_id == QuizAttempt.id)
        .where(attempt_filter, Question.quiz_id.in_(quiz_ids))
        .group_by(Question.difficulty)
    )
    by_difficulty = []
    for row in d_result:
        by_difficulty.append({
            "difficulty": row[0] or "medium",
            "total": row[1] or 0,
            "correct": row[2] or 0,
        })

    w_result = await db.execute(
        select(
            func.strftime('%Y-W%W', QuizAttempt.completed_at),
            func.avg(QuizAttempt.score * 1.0 / QuizAttempt.total * 100),
            func.count(QuizAttempt.id),
        )
        .where(attempt_filter, QuizAttempt.quiz_id.in_(quiz_ids))
        .group_by(func.strftime('%Y-W%W', QuizAttempt.completed_at))
        .order_by(func.strftime('%Y-W%W', QuizAttempt.completed_at).desc())
        .limit(8)
    )
    weekly_trend = []
    for row in reversed(list(w_result)):
        weekly_trend.append({
            "week": row[0] or "",
            "score_avg": round(row[1], 1) if row[1] else 0,
            "attempts": row[2] or 0,
        })

    sorted_kp = sorted(by_knowledge_point, key=lambda x: x["percentage"])
    weakest_points = [kp["name"] for kp in sorted_kp[:3] if kp["total"] > 0]

    return {
        "by_knowledge_point": by_knowledge_point,
        "by_difficulty": by_difficulty,
        "weekly_trend": weekly_trend,
        "total_quizzes": len(quiz_ids),
        "total_attempts": total_attempts,
        "overall_percentage": overall_percentage,
        "weakest_points": weakest_points,
    }


@router.get("/api/quiz/history/{course_id}")
async def quiz_history(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """练习历史列表（按时间倒序）"""
    quiz_ids_result = await db.execute(
        select(Quiz.id).where(Quiz.course_id == course_id)
    )
    quiz_ids = [row[0] for row in quiz_ids_result.all()]
    if not quiz_ids:
        return []

    a_result = await db.execute(
        select(QuizAttempt)
        .where(
            QuizAttempt.student_id == user.id,
            QuizAttempt.quiz_id.in_(quiz_ids),
        )
        .order_by(QuizAttempt.completed_at.desc())
    )
    attempts = a_result.scalars().all()

    quiz_map = {}
    if attempts:
        q_result = await db.execute(
            select(Quiz).where(Quiz.id.in_([a.quiz_id for a in attempts]))
        )
        for q in q_result.scalars().all():
            quiz_map[q.id] = q

    return [
        {
            "attempt_id": a.id,
            "quiz_id": a.quiz_id,
            "quiz_title": quiz_map[a.quiz_id].title if a.quiz_id in quiz_map else "",
            "score": a.score,
            "total": a.total,
            "percentage": round(a.score / a.total * 100, 1) if a.total else 0,
            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        }
        for a in attempts
    ]


# ─── 思维导图 ──────────────────────────────────────────

@router.get("/api/mindmap/{course_id}")
async def get_mindmap(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    mindmap = await generate_mindmap(course_id, course.name)
    return {"course_id": course_id, "course_name": course.name, "mindmap": mindmap}


# ─── 学习计划 ──────────────────────────────────────────


@router.get("/api/study-plan/{course_id}")
async def get_study_plan(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StudyPlan)
        .where(
            StudyPlan.student_id == user.id,
            StudyPlan.course_id == course_id,
        )
        .order_by(StudyPlan.created_at.desc())
        .limit(1)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        return {"plan": None}

    items_result = await db.execute(
        select(StudyPlanItem)
        .where(StudyPlanItem.plan_id == plan.id)
        .order_by(StudyPlanItem.day)
    )
    items = items_result.scalars().all()

    total = len(items)
    completed = sum(1 for i in items if i.is_completed)

    return {
        "plan": {
            "id": plan.id,
            "course_id": plan.course_id,
            "plan_json": json.loads(plan.plan_json) if isinstance(plan.plan_json, str) else plan.plan_json,
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
            "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
            "items": [
                {
                    "id": i.id,
                    "day": i.day,
                    "knowledge_point": i.knowledge_point,
                    "task_type": i.task_type,
                    "description": i.description,
                    "is_completed": bool(i.is_completed),
                    "completed_at": i.completed_at.isoformat() if i.completed_at else None,
                }
                for i in items
            ],
            "total_items": total,
            "completed_items": completed,
            "progress": round(completed / total * 100, 1) if total else 0,
        }
    }


@router.post("/api/study-plan/generate/{course_id}")
async def generate_study_plan(
    course_id: int,
    body: dict,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    days = min(int(body.get("days", 7)), 30)

    quiz_ids_result = await db.execute(
        select(Quiz.id).where(Quiz.course_id == course_id)
    )
    quiz_ids = [row[0] for row in quiz_ids_result.all()]

    weak_points = []
    if quiz_ids:
        stats_result = await db.execute(
            select(
                Question.knowledge_point,
                func.count(Answer.id),
                func.sum(Answer.is_correct),
            )
            .select_from(Answer)
            .join(Question, Answer.question_id == Question.id)
            .join(QuizAttempt, Answer.attempt_id == QuizAttempt.id)
            .where(
                QuizAttempt.student_id == user.id,
                Question.quiz_id.in_(quiz_ids),
            )
            .group_by(Question.knowledge_point)
        )
        for row in stats_result:
            kp = row[0] or "未分类"
            k_total = row[1] or 0
            k_correct = row[2] or 0
            accuracy = k_correct / k_total * 100 if k_total else 0
            if accuracy < 60:
                weak_points.append(kp)

    wrong_result = await db.execute(
        select(WrongBookRecord)
        .where(
            WrongBookRecord.student_id == user.id,
            WrongBookRecord.course_id == course_id,
        )
        .order_by(WrongBookRecord.created_at.desc())
    )
    wrong_records = wrong_result.scalars().all()
    wrong_point_topics = list(set(
        r.knowledge_point for r in wrong_records if r.knowledge_point
    ))

    kb_results = await search(course_id, f"{course.name} 知识点 目录 章节", top_k=10)
    kb_topics = [r.get("text", "")[:200] for r in kb_results if r.get("text")]

    prompt = f"""你是一个AI学习规划师。请为以下学生生成一份为期{days}天的学习计划。

课程: {course.name}
该学生在以下知识点上表现薄弱: {', '.join(weak_points) if weak_points else '暂无数据，请覆盖核心知识点'}
错题涉及: {', '.join(wrong_point_topics) if wrong_point_topics else '暂无错题记录'}
课程覆盖的知识点: {'; '.join(kb_topics) if kb_topics else '暂无课程知识库内容，请基于课程名称生成通用计划'}

请以JSON格式返回每日计划:
[
  {{
    "day": 1,
    "items": [
      {{"knowledge_point": "知识点名称", "task_type": "review", "description": "复习描述"}},
      {{"knowledge_point": "知识点名称", "task_type": "quiz", "description": "练习建议"}}
    ]
  }},
  ...
]

注意：
- 建议交替安排复习和练习
- 优先安排薄弱知识点在前几天
- 每天最多安排 3 项任务
- task_type 可选: review(知识点复习), quiz(练习题), chat_practice(与AI同学讨论)"""

    from app.services.llm import chat_completion
    raw = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        system_prompt="你是一个AI学习规划师。仅输出JSON，不要markdown代码块标记。",
        temperature=0.7,
        max_tokens=4096,
    )

    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("\n", 1)[0]
    if raw.startswith("```json"):
        raw = raw[7:]
    if raw.endswith("```"):
        raw = raw[:-3]

    try:
        plan_data = json.loads(raw)
        if isinstance(plan_data, dict) and "plan" in plan_data:
            plan_data = plan_data["plan"]
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="AI 生成计划失败，请重试")

    study_plan = StudyPlan(
        student_id=user.id,
        course_id=course_id,
        plan_json=json.dumps(plan_data, ensure_ascii=False),
    )
    db.add(study_plan)
    await db.flush()

    all_items = []
    for day_entry in plan_data:
        day_num = day_entry.get("day", 1)
        for item in day_entry.get("items", []):
            all_items.append(StudyPlanItem(
                plan_id=study_plan.id,
                day=day_num,
                knowledge_point=item.get("knowledge_point", ""),
                task_type=item.get("task_type", "review"),
                description=item.get("description", ""),
            ))

    for item in all_items:
        db.add(item)

    await db.commit()
    await db.refresh(study_plan)

    return {"id": study_plan.id, "total_items": len(all_items), "days": len(plan_data)}


@router.post("/api/study-plan/item/{item_id}/complete")
async def complete_plan_item(
    item_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StudyPlanItem)
        .where(StudyPlanItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="计划项不存在")

    plan_result = await db.execute(select(StudyPlan).where(StudyPlan.id == item.plan_id))
    plan = plan_result.scalar_one_or_none()
    if not plan or plan.student_id != user.id:
        raise HTTPException(status_code=403, detail="无权限")

    item.is_completed = 1 if not item.is_completed else 0
    item.completed_at = datetime.utcnow() if item.is_completed else None
    await db.commit()

    return {"id": item.id, "is_completed": bool(item.is_completed)}


@router.post("/api/study-plan/{plan_id}/regenerate")
async def regenerate_study_plan(
    plan_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    plan_result = await db.execute(select(StudyPlan).where(StudyPlan.id == plan_id))
    plan = plan_result.scalar_one_or_none()
    if not plan or plan.student_id != user.id:
        raise HTTPException(status_code=403, detail="无权限")

    items_result = await db.execute(
        select(StudyPlanItem)
        .where(StudyPlanItem.plan_id == plan.id)
        .order_by(StudyPlanItem.day)
    )
    items = items_result.scalars().all()
    completed_points = list(set(
        i.knowledge_point for i in items if i.is_completed
    ))

    course_result = await db.execute(select(Course).where(Course.id == plan.course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    kb_results = await search(plan.course_id, f"{course.name} 知识点 目录 章节", top_k=10)
    kb_topics = [r.get("text", "")[:200] for r in kb_results if r.get("text")]

    prompt = f"""你是一个AI学习规划师。请为以下学生生成一份新的学习计划。

课程: {course.name}
该学生已完成的知识点: {', '.join(completed_points) if completed_points else '暂无'}
课程覆盖的知识点: {'; '.join(kb_topics) if kb_topics else '暂无'}

请根据已完成的知识点，着重规划未覆盖或需要加强的知识点。
以JSON格式返回每日计划，格式同上，为期7天。"""

    from app.services.llm import chat_completion
    raw = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        system_prompt="你是一个AI学习规划师。仅输出JSON，不要markdown代码块标记。",
        temperature=0.7,
        max_tokens=4096,
    )

    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("\n", 1)[0]
    if raw.startswith("```json"):
        raw = raw[7:]
    if raw.endswith("```"):
        raw = raw[:-3]

    try:
        plan_data = json.loads(raw)
        if isinstance(plan_data, dict) and "plan" in plan_data:
            plan_data = plan_data["plan"]
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="AI 重新生成计划失败，请重试")

    await db.execute(
        select(StudyPlanItem).where(StudyPlanItem.plan_id == plan.id)
    )
    items_result = await db.execute(
        select(StudyPlanItem).where(StudyPlanItem.plan_id == plan.id)
    )
    for old_item in items_result.scalars().all():
        await db.delete(old_item)

    plan.plan_json = json.dumps(plan_data, ensure_ascii=False)
    plan.updated_at = datetime.utcnow()

    all_items = []
    for day_entry in plan_data:
        day_num = day_entry.get("day", 1)
        for item in day_entry.get("items", []):
            all_items.append(StudyPlanItem(
                plan_id=plan.id,
                day=day_num,
                knowledge_point=item.get("knowledge_point", ""),
                task_type=item.get("task_type", "review"),
                description=item.get("description", ""),
            ))

    for item in all_items:
        db.add(item)

    await db.commit()
    return {"id": plan.id, "total_items": len(all_items), "days": len(plan_data)}


@router.get("/api/study-plan/daily-recommend/{course_id}")
async def get_daily_recommend(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """轻量版：每次返回当天的 3 条学习推荐"""
    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    wrong_result = await db.execute(
        select(WrongBookRecord)
        .where(
            WrongBookRecord.student_id == user.id,
            WrongBookRecord.course_id == course_id,
        )
        .order_by(WrongBookRecord.created_at.desc())
        .limit(5)
    )
    wrong_records = wrong_result.scalars().all()
    weak_info = "; ".join(
        f"{r.knowledge_point}: {r.question_content[:50]}"
        for r in wrong_records if r.knowledge_point
    ) if wrong_records else "暂无"

    prompt = f"""你是AI学习助手。为以下课程的学生推荐今天要学习的3项任务。
课程: {course.name}
最近错题: {weak_info}

返回JSON数组，每项包含 knowledge_point, task_type (review/quiz/chat_practice), description。
最多3项，优先薄弱知识点。"""

    from app.services.llm import chat_completion
    raw = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        system_prompt="仅输出JSON数组，不要markdown。",
        temperature=0.7,
        max_tokens=1024,
    )

    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("\n", 1)[0]
    if raw.startswith("```json"):
        raw = raw[7:]
    if raw.endswith("```"):
        raw = raw[:-3]

    try:
        items = json.loads(raw)
        return {"items": items[:3]}
    except json.JSONDecodeError:
        return {"items": [
            {"knowledge_point": course.name, "task_type": "review", "description": f"复习{course.name}核心概念"},
            {"knowledge_point": course.name, "task_type": "quiz", "description": f"做一套{course.name}练习题"},
            {"knowledge_point": course.name, "task_type": "chat_practice", "description": f"与AI同学讨论{course.name}疑难问题"},
        ]}
