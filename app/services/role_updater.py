import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.course import Course
from app.services.analytics import analyze_conversations, generate_report
from app.services.llm import chat_completion


async def update_student_roles(
    course_id: int,
    db: AsyncSession | None = None,
) -> dict:
    close_db = db is None
    if db is None:
        async with async_session() as db:
            return await update_student_roles(course_id, db=db)

    data = await analyze_conversations(course_id, days=7, db=db)

    if not data["top10"] and not data["weak_tags"]:
        return {"message": "数据不足，暂无法更新角色", "updated": False}

    top5 = data["top10"][:5]
    weak_tags = data["weak_tags"]

    top5_text = "\n".join(
        f"{i+1}. {item['tag']}（{item['count']}次）"
        for i, item in enumerate(top5)
    )
    weak_text = "、".join(weak_tags) if weak_tags else "暂未发现明显薄弱点"

    prompt = f"""你是一位课程教学设计专家。以下是一个班级最近7天的学习数据：

高频问题 TOP5：
{top5_text}

薄弱知识点：{weak_text}

请根据以上学情，为以下四类 AI 学生角色生成新的提问倾向描述（直接更新他们的 prompt），
使他们在未来一周能更有针对性地提问，覆盖班级的学习薄弱环节。

角色列表：
1. 基础小问（基础薄弱型）- 需要围绕最基本概念提问
2. 中坚小固（中等巩固型）- 关注考点和易错点
3. 拓思考（拓展思考型）- 追求深层原理
4. 学长知喻（AI学长）- 学习方法指导+应试技巧

请返回 JSON 格式，key 为角色名，value 为新的提问倾向描述（中文，30-50字）。"""
    result = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6,
    )

    updates = {}
    try:
        updates = json.loads(result)
    except json.JSONDecodeError:
        pass

    result_obj = await db.execute(select(Course).where(Course.id == course_id))
    course = result_obj.scalar_one_or_none()
    if not course:
        return {"message": "课程不存在", "updated": False}

    existing_config = {}
    if course.student_roles_config:
        try:
            existing_config = json.loads(course.student_roles_config)
        except json.JSONDecodeError:
            existing_config = {}

    for role_name, new_prompt in updates.items():
        if role_name in existing_config:
            existing_config[role_name]["prompt"] = new_prompt
        else:
            existing_config[role_name] = {"prompt": new_prompt}

    course.student_roles_config = json.dumps(existing_config, ensure_ascii=False)
    await db.commit()

    return {
        "message": "AI 学生角色已更新",
        "updated": True,
        "updated_roles": list(updates.keys()),
        "summary": f"基于本周高频问题 {len(top5)} 个、薄弱知识点 {len(weak_tags)} 个完成角色迭代",
    }


async def trigger_analysis(course_id: int) -> dict:
    async with async_session() as db:
        report_data = await generate_report(course_id, db=db)
        role_result = await update_student_roles(course_id, db=db)
    return {
        "report": report_data,
        "role_update": role_result,
    }
