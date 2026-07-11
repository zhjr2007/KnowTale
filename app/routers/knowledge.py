from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path

from app.database import get_db
from app.dependencies import require_teacher, require_user
from app.models.user import User
from app.models.course import Course
from app.models.knowledge import KnowledgeDocument
from app.services.document_parser import parse_document
from app.services.rag import index_document, search, clear_course_knowledge, get_chunk_count

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)


@router.post("/upload/{course_id}")
async def upload_document(
    course_id: int,
    file: UploadFile = File(...),
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course or course.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该课程")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".pdf", ".docx", ".doc", ".pptx", ".ppt", ".txt", ".md"):
        raise HTTPException(status_code=400, detail="不支持的文件格式")

    save_path = UPLOADS_DIR / f"{course_id}_{file.filename}"
    content = await file.read()
    save_path.write_bytes(content)

    parsed = await parse_document(save_path)
    if not parsed.strip():
        raise HTTPException(status_code=400, detail="文档解析失败，内容为空")

    chunk_count = await index_document(course_id, parsed, {"filename": file.filename})

    doc = KnowledgeDocument(
        course_id=course_id,
        filename=file.filename,
        file_path=str(save_path),
        file_type=ext,
        chunk_count=chunk_count,
    )
    db.add(doc)
    await db.commit()

    return {
        "message": "上传并索引成功",
        "filename": file.filename,
        "chunk_count": chunk_count,
    }


@router.get("/documents/{course_id}")
async def list_documents(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.course_id == course_id)
        .order_by(KnowledgeDocument.uploaded_at.desc())
    )
    docs = result.scalars().all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "file_type": d.file_type,
            "chunk_count": d.chunk_count,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        }
        for d in docs
    ]


@router.delete("/documents/{course_id}/{doc_id}")
async def delete_document(
    course_id: int,
    doc_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == doc_id,
            KnowledgeDocument.course_id == course_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    path = Path(doc.file_path)
    if path.exists():
        path.unlink()

    await db.delete(doc)
    await db.commit()
    return {"message": "已删除"}


@router.post("/rebuild/{course_id}")
async def rebuild_knowledge(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    await clear_course_knowledge(course_id)

    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.course_id == course_id)
    )
    docs = result.scalars().all()

    total = 0
    for doc in docs:
        path = Path(doc.file_path)
        if path.exists():
            parsed = await parse_document(path)
            count = await index_document(course_id, parsed, {"filename": doc.filename})
            doc.chunk_count = count
            total += count

    await db.commit()
    return {"message": "知识库重建完成", "total_chunks": total}


@router.get("/stats/{course_id}")
async def knowledge_stats(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.course_id == course_id)
    )
    docs = result.scalars().all()
    chunk_count = await get_chunk_count(course_id)

    return {
        "document_count": len(docs),
        "chunk_count": chunk_count,
        "documents": [
            {"filename": d.filename, "chunk_count": d.chunk_count}
            for d in docs
        ],
    }
