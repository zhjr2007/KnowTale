import json
from app.services.llm import chat_completion
from app.services.rag import get_chunk_count, retrieve

GENERATE_QUIZ_PROMPT = """你是一个专业出题教师。根据课程知识内容，生成一套练习题。
输出严格为JSON数组格式（不要markdown代码块标记），每题格式：
{
    "content": "题目内容",
    "type": "choice" 或 "short_answer",
    "options": ["A. 选项A", "B. 选项B", "C. 选项C", "D. 选项D"]  (选择题必填),
    "answer": "正确答案",
    "knowledge_point": "所属知识点",
    "difficulty": "easy/medium/hard"
}

要求：
- 选择题和简答题混合
- 覆盖不同难度层级
- 每道题关联具体知识点
- 答案准确、解析简洁"""


async def generate_quiz(
    course_id: int,
    course_name: str,
    num_questions: int = 5,
    difficulty: str = "mixed",
    focus: str | None = None,
) -> list[dict]:
    chunk_count = await get_chunk_count(course_id)
    if chunk_count == 0:
        samples = [
            {"content": f"什么是{course_name}的核心概念？", "type": "short_answer", "answer": f"{course_name}是..."},
            {"content": f"{course_name}主要应用在哪些领域？", "type": "short_answer", "answer": "主要应用于..."},
        ]
        return samples[:num_questions]

    results = await retrieve(course_id, f"{course_name} 核心知识点 考试重点", top_k=10)
    context = "\n\n".join(r["text"][:500] for r in results if r.get("text"))

    focus_prompt = f"\n重点关注：{focus}" if focus else ""
    prompt = f"""课程名称：{course_name}
课程知识内容：
{context}

请生成{num_questions}道{_difficulty_label(difficulty)}练习题。{focus_prompt}"""

    raw = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=GENERATE_QUIZ_PROMPT,
        temperature=0.8,
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
        questions = json.loads(raw)
        if isinstance(questions, dict) and "questions" in questions:
            questions = questions["questions"]
        return questions[:num_questions]
    except json.JSONDecodeError:
        return _fallback_questions(course_name, num_questions)


async def grade_short_answer(
    question: str,
    correct_answer: str,
    student_answer: str,
) -> tuple[bool, str]:
    prompt = f"""作为教师，判断学生的简答题答案是否正确。

题目：{question}
参考答案：{correct_answer}
学生答案：{student_answer}

请判断：学生答案的核心观点是否正确？输出JSON格式：
{{"is_correct": true/false, "feedback": "简短评语，指出对错原因和改进建议"}}"""

    raw = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        system_prompt="你是一位严格的但鼓励性的教师。仅输出JSON，不要markdown。",
        temperature=0.3,
        max_tokens=512,
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
        result = json.loads(raw)
        return bool(result.get("is_correct", False)), result.get("feedback", "")
    except json.JSONDecodeError:
        return False, "判分失败，请手动批改"


async def generate_mindmap(course_id: int, course_name: str) -> str:
    results = await retrieve(course_id, f"{course_name} 目录 章节 大纲", top_k=15)
    context = "\n\n".join(r["text"][:800] for r in results if r.get("text"))

    prompt = f"""根据以下课程内容，生成思维导图的Markdown层级结构（使用 # ## ### 表示层级）。
课程名称：{course_name}

内容：
{context}

输出示例：
# {course_name}
## 第一章
### 1.1 节标题
- 知识点1
- 知识点2
### 1.2 节标题
## 第二章
...

只输出Markdown结构，不要多余说明。"""

    result = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=2048,
    )
    return result


async def generate_review_question(course_id: int, course_name: str, used_points: list[str]) -> dict | None:
    results = await retrieve(course_id, f"{course_name} 核心概念 定义 知识点", top_k=20)
    used_str = "、".join(used_points[-10:]) if used_points else "无"

    prompt = f"""从课程知识中选一个未使用过的知识点生成抽背题。
课程：{course_name}
已抽取的知识点：{used_str}

输出JSON：
{{"question": "问题内容", "answer": "参考答案", "knowledge_point": "知识点名称"}}"""

    raw = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        system_prompt="仅输出JSON，不要markdown代码块。",
        temperature=0.7,
        max_tokens=512,
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
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def generate_wrong_book_quiz(records: list[dict], course_name: str) -> list[dict]:
    points = "\n".join(f"- {r['knowledge_point']}: {r['question_content'][:100]}" for r in records)
    prompt = f"""以下是学生在{course_name}课程中的错题记录。请针对这些薄弱知识点，生成5道巩固练习题。
错题记录：
{points}

按之前格式输出JSON数组。"""

    raw = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=GENERATE_QUIZ_PROMPT,
        temperature=0.8,
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
        questions = json.loads(raw)
        if isinstance(questions, dict) and "questions" in questions:
            questions = questions["questions"]
        return questions
    except json.JSONDecodeError:
        return []


def _difficulty_label(d: str) -> str:
    return {"easy": "简单", "medium": "中等", "hard": "困难", "mixed": "混合难度"}.get(d, "混合难度")


def _fallback_questions(course_name: str, n: int) -> list[dict]:
    templates = [
        {"content": f"简述{course_name}的核心概念。", "type": "short_answer", "options": None, "answer": "请参考教材", "knowledge_point": "基本概念", "difficulty": "easy"},
        {"content": f"以下哪个不是{course_name}的主要特征？", "type": "choice", "options": ["A. 特征一", "B. 特征二", "C. 特征三", "D. 特征四"], "answer": "D", "knowledge_point": "基本概念", "difficulty": "easy"},
        {"content": f"请解释{course_name}中最重要的三个原理。", "type": "short_answer", "options": None, "answer": "请参考教材", "knowledge_point": "核心原理", "difficulty": "medium"},
    ]
    while len(templates) < n:
        templates.append(templates[0])
    return templates[:n]
