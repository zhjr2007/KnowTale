import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "知喻")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'knowtale.db'}",
    )

    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", "knowtale-secret-key-change-in-production"
    )
    JWT_EXPIRATION_HOURS: int = int(os.getenv("JWT_EXPIRATION_HOURS", "168"))
    JWT_ALGORITHM: str = "HS256"

    BAILIAN_API_KEY: str = os.getenv("BAILIAN_API_KEY", "")
    BAILIAN_BASE_URL: str = os.getenv(
        "BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen-plus")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")
    RERANK_MODEL: str = os.getenv("RERANK_MODEL", "text-rerank-v1")

    MINERU_URL: str = os.getenv("MINERU_URL", "http://localhost:8001")

    CHROMA_HOST: str = os.getenv("CHROMA_HOST", "localhost")
    CHROMA_PORT: int = int(os.getenv("CHROMA_PORT", "8000"))

    @property
    def CHROMA_URL(self) -> str:
        return f"http://{self.CHROMA_HOST}:{self.CHROMA_PORT}"


settings = Settings()
