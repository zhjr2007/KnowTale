from contextlib import asynccontextmanager
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, pass_context
from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import init_db
from app.dependencies import get_current_user, require_user
from app.database import get_db
from app.models.user import User
from app.routers import auth, courses, knowledge, tools

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR.parent / "static"


_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    auto_reload=settings.DEBUG,
)


def render_template(name: str, **context) -> HTMLResponse:
    template = _jinja_env.get_template(name)
    return HTMLResponse(template.render(**context))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(knowledge.router)
app.include_router(tools.router)


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")


@app.get("/login")
async def login_page(request: Request, user: User = Depends(get_current_user)):
    if user:
        return RedirectResponse(url="/dashboard")
    return render_template("login.html", request=request, user=None)


@app.get("/register")
async def register_page(request: Request, user: User = Depends(get_current_user)):
    if user:
        return RedirectResponse(url="/dashboard")
    return render_template("register.html", request=request, user=None)


@app.get("/dashboard")
async def dashboard(
    request: Request,
    user: User = Depends(require_user),
):
    return render_template("dashboard.html", request=request, user=user)


@app.get("/courses/{course_id}")
async def course_detail(
    request: Request,
    course_id: int,
    user: User = Depends(require_user),
):
    return render_template("course_detail.html", request=request, user=user, course_id=course_id)


@app.get("/knowledge/{course_id}")
async def knowledge_page(
    request: Request,
    course_id: int,
    user: User = Depends(require_user),
):
    return render_template("knowledge.html", request=request, user=user, course_id=course_id)


@app.get("/quiz/{quiz_id}")
async def quiz_page(
    request: Request,
    quiz_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.quiz import Quiz, Question
    from sqlalchemy import select
    q_result = await db.execute(select(Quiz).where(Quiz.id == quiz_id))
    quiz = q_result.scalar_one_or_none()
    if not quiz:
        return RedirectResponse(url="/dashboard")
    qs_result = await db.execute(
        select(Question).where(Question.quiz_id == quiz_id)
    )
    questions = qs_result.scalars().all()
    import json
    return render_template(
        "quiz.html",
        request=request, user=user,
        quiz={"id": quiz.id, "title": quiz.title},
        course_id=quiz.course_id,
        course_name=quiz.course.name if quiz.course else "",
        questions=[
            {
                "id": q.id, "content": q.content,
                "type": q.question_type,
                "options": json.loads(q.options) if q.options else None,
                "knowledge_point": q.knowledge_point,
                "difficulty": q.difficulty,
            }
            for q in questions
        ],
    )


@app.get("/quiz/{quiz_id}/result/{attempt_id}")
async def quiz_result_page(
    request: Request,
    quiz_id: int,
    attempt_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.quiz import QuizAttempt, Answer, Question
    from sqlalchemy import select
    a_result = await db.execute(
        select(QuizAttempt).where(
            QuizAttempt.id == attempt_id,
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.student_id == user.id,
        )
    )
    attempt = a_result.scalar_one_or_none()
    if not attempt:
        return RedirectResponse(url="/dashboard")

    ans_result = await db.execute(
        select(Answer).where(Answer.attempt_id == attempt_id)
    )
    answers = ans_result.scalars().all()

    details = []
    for a in answers:
        q_result = await db.execute(select(Question).where(Question.id == a.question_id))
        q = q_result.scalar_one_or_none()
        if q:
            details.append({
                "content": q.content,
                "student_answer": a.student_answer,
                "correct_answer": q.correct_answer,
                "is_correct": a.is_correct,
                "feedback": a.feedback,
            })

    qz_result = await db.execute(select(Quiz).where(Quiz.id == quiz_id))
    quiz = qz_result.scalar_one_or_none()

    return render_template(
        "quiz_result.html",
        request=request, user=user,
        score=attempt.score, total=attempt.total,
        percentage=round(attempt.score / attempt.total * 100, 1) if attempt.total else 0,
        details=details,
        course_id=quiz.course_id if quiz else 0,
    )


@app.get("/wrong-book/{course_id}")
async def wrong_book_page(
    request: Request,
    course_id: int,
    user: User = Depends(require_user),
):
    return render_template("wrong_book.html", request=request, user=user, course_id=course_id)


@app.get("/review/{course_id}")
async def review_page(
    request: Request,
    course_id: int,
    user: User = Depends(require_user),
):
    return render_template("review.html", request=request, user=user, course_id=course_id)


@app.get("/mindmap/{course_id}")
async def mindmap_page(
    request: Request,
    course_id: int,
    user: User = Depends(require_user),
):
    return render_template("mindmap.html", request=request, user=user, course_id=course_id)


@app.get("/quiz/list/{course_id}")
async def quiz_list_page(
    request: Request,
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.course import Course
    from sqlalchemy import select
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    return render_template(
        "quiz_list.html", request=request, user=user,
        course_id=course_id, course_name=course.name if course else "",
    )
