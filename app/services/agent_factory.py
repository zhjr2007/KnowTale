import json
from typing import Any

from app.services.llm import chat_completion

TEACHER_PROMPT = """你是一个AI教师角色卡生成器。根据课程信息和教学风格，生成JSON格式的角色卡。
输出格式（仅输出JSON，不要包含markdown代码块标记）：
{
    "name": "教师名称",
    "personality": "人设定位描述",
    "teaching_style": "教学风格描述",
    "dialogue_style": "对话风格",
    "greeting": "开场白",
    "knowledge_boundary": "知识边界说明",
    "world_book": ["关键教学原则条目"]
}"""

STUDENT_TEMPLATES = {
    "basic": {
        "name": "基础小问",
        "type_desc": "基础薄弱型学生",
        "personality": "学习进度较慢，需要从最基本概念开始理解，不太敢在课堂上提问",
        "dialogue_style": "语气谦逊、带有不确定感，常用'这个我不太懂''能再解释一下吗'等表达",
        "greeting": "大家好，我是基础小问😊 我基础比较差，可能会问很多简单问题，请大家多多包涵！",
        "question_focus": "入门概念、基础定义、简单例题",
    },
    "medium": {
        "name": "中坚小固",
        "type_desc": "中等巩固型学生",
        "personality": "基础较好，但需要反复巩固考点和易错点，注重应试技巧",
        "dialogue_style": "语气认真务实，喜欢追问'这个会考吗''考试会怎么出题'",
        "greeting": "大家好，我是中坚小固📚 我会重点关注考点和易错题，一起加油备考！",
        "question_focus": "考点解析、易错点辨析、作业答疑",
    },
    "advanced": {
        "name": "拓思考",
        "type_desc": "拓展思考型学生",
        "personality": "基础扎实，喜欢追问更深层原理和跨学科联系，经常提出开放性问题",
        "dialogue_style": "语气好奇且带有思辨性，常用'这是为什么呢''如果...会怎样'",
        "greeting": "大家好，我是拓思考💡 我喜欢问为什么，希望能和大家一起把知识吃透！",
        "question_focus": "延伸性问题、开放性讨论、实际应用",
    },
    "senior": {
        "name": "学长知喻",
        "type_desc": "AI学长/学姐",
        "personality": "经验丰富，熟悉课程重难点和考试规律，善于传授学习方法和应试技巧",
        "dialogue_style": "语气亲切老练，乐于分享经验，常用'根据往年经验''建议你们'",
        "greeting": "同学们好，我是学长知喻🎓 这门课我'修过'，有什么学习方法和考试问题都可以问我！",
        "question_focus": "学习方法指导、应试技巧、经验分享",
    },
}


async def generate_teacher_role(
    course_name: str,
    course_description: str,
    teaching_style: str = "温和耐心，循循善诱",
) -> dict[str, Any]:
    prompt = f"""课程名称：{course_name}
课程描述：{course_description}
教学风格：{teaching_style}

请根据以上信息生成AI教师的JSON角色卡。"""
    user_msg = {"role": "user", "content": prompt}

    result = await chat_completion(
        messages=[user_msg],
        system_prompt=TEACHER_PROMPT,
        temperature=0.8,
    )

    result = result.strip()
    if result.startswith("```"):
        result = result.split("\n", 1)[1]
        result = result.rsplit("\n", 1)[0]
    if result.startswith("```json"):
        result = result[7:]
    if result.endswith("```"):
        result = result[:-3]

    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {
            "name": f"{course_name}AI教师",
            "personality": f"精通{course_name}的专业教师",
            "teaching_style": teaching_style,
            "dialogue_style": "专业、耐心、条理清晰",
            "greeting": f"同学们好，我是{course_name}的AI教师，有任何课程问题都可以问我。",
            "knowledge_boundary": f"主要回答{course_name}课程相关的问题",
            "world_book": ["基于课程知识库回答", "明确标注课外内容"],
        }


async def generate_student_role(
    student_type: str,
    course_name: str,
    course_description: str,
) -> dict[str, Any]:
    template = STUDENT_TEMPLATES.get(student_type)
    if not template:
        template = STUDENT_TEMPLATES["basic"]

    system_prompt = f"""你是一个AI学生角色卡生成器。根据课程信息和学生类型，生成JSON格式的角色设定。
输出格式（仅JSON）：
{{
    "name": "{template['name']}",
    "type": "{template['type_desc']}",
    "personality": "{template['personality']} 结合课程{course_name}的具体内容调整",
    "dialogue_style": "{template['dialogue_style']}",
    "greeting": "结合课程{course_name}的个性化开场白",
    "question_focus": "{template['question_focus']}",
    "question_examples": ["示例问题1", "示例问题2", "示例问题3"]
}}"""

    prompt = f"""课程名称：{course_name}
课程描述：{course_description}
学生类型：{template['type_desc']}

请生成这个AI学生的角色设定JSON。"""

    result = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=system_prompt,
        temperature=0.8,
    )

    result = result.strip()
    if result.startswith("```"):
        result = result.split("\n", 1)[1]
        result = result.rsplit("\n", 1)[0]
    if result.startswith("```json"):
        result = result[7:]
    if result.endswith("```"):
        result = result[:-3]

    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {
            "name": template["name"],
            "type": template["type_desc"],
            "personality": template["personality"],
            "dialogue_style": template["dialogue_style"],
            "greeting": f"大家好，我是{template['name']}，很高兴和大家一起学习{course_name}！",
            "question_focus": template["question_focus"],
            "question_examples": [],
        }


def get_student_templates() -> dict:
    return {k: {"name": v["name"], "type_desc": v["type_desc"]} for k, v in STUDENT_TEMPLATES.items()}
