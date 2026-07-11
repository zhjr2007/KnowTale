from contextlib import asynccontextmanager
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, pass_context
from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.dependencies import get_current_user, require_user
from app.models.user import User
from app.routers import auth, courses, knowledge

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
