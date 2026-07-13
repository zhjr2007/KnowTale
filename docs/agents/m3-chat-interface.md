# M3: AI 角色对话界面（SSE 实时流式聊天）

## 目标

实现多参与者实时聊天界面，让真人学生可以同时与 AI 教师和 4 种 AI 学生进行对话。使用 SSE（Server-Sent Events）实现流式消息推送。

## 技术上下文

- **项目根目录**: `D:\KnowTale`
- **相关文件**:
  - `app/models/conversation.py` — Conversation 模型（已有：course_id, speaker_type, speaker_id, content, knowledge_tag, created_at）
  - `app/services/agent_factory.py` — `generate_teacher_role()`, `generate_student_role()`, `get_default_speech_rules()`
  - `app/services/llm.py` — `chat_completion()`（stream 模式）
  - `app/services/analytics.py` — 对话分析服务（后续关联）
  - `app/routers/` — 需新建 `chat.py`
  - `app/services/` — 需新建 `chat_service.py`
  - `app/templates/` — 需新建 `chat.html`
  - `app/templates/course_detail.html` — 聊天 tab 目前显示"即将上线"，需替换为嵌入或跳转
  - `app/main.py` — 注册新路由
- **数据模型**:
  - Conversation: id, course_id, speaker_type(ai_teacher/ai_student/student), speaker_id, content, knowledge_tag, created_at
  - Course: teacher_role_card(JSON), student_roles_config(JSON)
- **AI 角色**:
  - AI 教师: 从 `course.teacher_role_card` 获取角色卡
  - 4 种 AI 学生: basic(基础小问), medium(中坚小固), advanced(拓思考), senior(学长知喻)
- **SSE 技术**:
  - 后端: FastAPI StreamingResponse + async generator
  - 前端: EventSource API

## 实现任务

### 1. [后端] 创建聊天服务

新建 `app/services/chat_service.py`：

```python
async def process_student_message(
    course_id: int,
    student_id: int,
    message: str,
    db: AsyncSession,
):
    """
    1. 保存学生消息到 Conversation 表（speaker_type="student"）
    2. 从 course.teacher_role_card 获取 AI 教师角色卡
    3. 从 course.student_roles_config 获取 AI 学生配置
    4. 调用 RAG search 获取相关知识
    5. 构建 AI 教师 system prompt（角色卡 + 知识上下文 + 对话历史摘要）
    6. 调用 llm.chat_completion 流式生成 AI 教师回复
    7. 将回复保存到 Conversation（speaker_type="ai_teacher"）
    8. 返回流式生成的文本块
    """
```

流式生成函数（SSE 用）：

```python
async def stream_teacher_response(
    course_id: int,
    student_id: int,
    message: str,
    db: AsyncSession,
):
    """
    Async generator that yields SSE event strings.
    Step by step using yield for streaming updates.
    """
    # yield f"data: {json.dumps({'type': 'status', 'message': '正在思考...'})}\n\n"

    # 1. 保存用户消息
    # 2. 查询 RAG
    # 3. 构建 prompt
    # 4. 流式调用 LLM
    #    async for chunk in await chat_completion(..., stream=True):
    #        yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
    # 5. 保存完整回复
    # 6. 信号 AI 学生参与（可选）
    # yield "data: [DONE]\n\n"
```

### 2. [后端] 创建聊天路由

新建 `app/routers/chat.py`：

```python
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import require_user
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/api/chat", tags=["chat"])
```

```python
@router.post("/send/{course_id}")
async def send_message(
    course_id: int,
    message: str = Form(...),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    非流式入口（用于简单场景），
    返回 AI 教师完整回复 + AI 学生可能插入的回复。
    返回 JSON: { "reply": str, "ai_student_reply": str|None }
    """
```

```python
@router.get("/stream/{course_id}")
async def stream_chat(
    course_id: int,
    message: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    SSE 流式接口。返回 StreamingResponse。
    message 通过 query parameter 传递（简化实现）。
    事件类型：
      - token: AI 教师回复的文本块
      - student_typing: AI 学生开始"打字"
      - student_token: AI 学生回复的文本块
      - status: 状态更新消息
      - error: 错误信息
    """
    return StreamingResponse(
        stream_teacher_response(course_id, user.id, message, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
```

```python
@router.get("/history/{course_id}")
async def get_history(
    course_id: int,
    before_id: Optional[int] = None,
    limit: int = 50,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取聊天历史。
    支持 before_id 分页（加载更早的消息）。
    返回按 created_at ASC 排序的消息列表。
    每条消息格式: { id, speaker_type, speaker_id, speaker_name, content, knowledge_tag, created_at }
    """
```

### 3. [前端] 聊天页面

新建 `app/templates/chat.html`，继承 `base.html`：

**布局**：
- 左侧：参与者列表（真人学生自己 + AI 教师 + 4 种 AI 学生）
  - 每个参与者显示头像（圆形，不同颜色区分角色）+ 名称 + 在线绿点
  - AI 教师：特殊金色边框标识
- 右侧主体：消息流区域

**消息流**：
- 消息从左到右或右到左排列（类似常见 IM）
- 真人学生消息：右对齐，蓝色气泡
- AI 教师消息：左对齐，金色边框气泡，带"AI 教师"标签
- AI 学生消息：左对齐，各自颜色气泡，带类型标签（基础小问 / 中坚小固 / 拓思考 / 学长知喻）
- 气泡内支持 Markdown 渲染（`marked` CDN 或简单正则替换）
- 流式显示：AI 回复逐字出现（类似打字机效果）

**输入区域**：
- 底部固定 input 框（类似微信）
- 发送按钮
- Enter 发送，Shift+Enter 换行
- 发送后禁用输入，等待 AI 回复完成后重新启用
- 输入框自适应高度

**打字指示器**：
- AI 教师思考时显示 "AI 教师正在输入..."
- AI 学生思考时显示 "基础小问 正在输入..."

**SSE 连接**：

```javascript
const eventSource = new EventSource(`/api/chat/stream/${courseId}?message=${encodeURIComponent(msg)}`);
eventSource.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === 'token') {
        // 追加到 AI 教师气泡
    } else if (data.type === 'student_token') {
        // 追加到对应 AI 学生气泡
    } else if (data.type === 'status') {
        // 显示状态信息
    }
};
eventSource.addEventListener('error', () => {
    // 重连或显示错误
});
eventSource.addEventListener('end', () => {
    eventSource.close();
});
```

### 4. [前端] 集成到课程详情页

修改 `app/templates/course_detail.html` 中的"聊天"tab：

- 将原本的"即将上线"占位符替换为 iframe 或链接跳转到 `/chat/{course_id}`
- 推荐：直接在 tab 内容区域嵌入聊天界面

注册路由到 `app/main.py`:

```python
@app.get("/chat/{course_id}")
async def chat_page(
    request: Request,
    course_id: int,
    user: User = Depends(require_user),
):
    return render_template("chat.html", request=request, user=user, course_id=course_id)
```

### 5. [后端] AI 学生参与逻辑（进阶）

在 `chat_service.py` 中实现 AI 学生自动触发参与：

- 根据 `student_roles_config` 中的 `activity_level` 概率决定是否参与
- 如果 AI 学生参与：
  1. 构建该 AI 学生的 system prompt（角色卡 + 当前对话上下文）
  2. 调用 LLM 简短生成（1-2 句话）
  3. 通过 SSE 推送到前端（`student_typing` → `student_token`）
  4. 保存到 Conversation 表

## 验收标准

- [ ] SSE 流式连接正常，AI 教师回复逐字显示
- [ ] 多参与者消息流显示正确（真人学生、AI 教师、AI 学生）
- [ ] 消息气泡带角色标识（颜色/标签）且风格分明
- [ ] 聊天历史加载正常（分页加载更多）
- [ ] 发送消息后自动滚动到底部
- [ ] 打字指示器正常显示
- [ ] 消息中的 Markdown 正确渲染
- [ ] 课程详情页"聊天"tab 可进入聊天界面
- [ ] 所有消息保存到 Conversation 表
- [ ] 无导入错误，app 正常启动

## 参考代码模式

- SSE 后端实现参考 FastAPI 官方文档 StreamingResponse + async generator 模式
- LLM 流式调用参考 `app/services/llm.py` 中 `chat_completion` 的 `stream` 参数
- 角色卡获取参考 `app/services/agent_factory.py` 中 `generate_teacher_role` 的输出格式
- RAG 检索参考 `app/services/rag.py` 的 `search()` 函数
- 前端布局参考 `templates/analytics.html` 的双栏布局结构
- 颜色系统：AI 教师 `#FFD700` 金色, basic `#4CAF50` 绿, medium `#2196F3` 蓝, advanced `#9C27B0` 紫, senior `#FF9800` 橙
