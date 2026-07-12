import json
import random
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_user
from app.models.user import User
from app.models.course import Course
from app.models.quiz import Quiz, Question, QuizAttempt, Answer, WrongBookRecord
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
