# M4b: AI 学习计划生成

## 目标

基于学生的错题记录、薄弱知识点和答题历史，利用 AI 自动生成个性化的每日学习计划，包含复习建议和练习推荐。

## 技术上下文

- **项目根目录**: `D:\KnowTale`
- **相关文件**:
  - `app/models/` — 需新建 `study_plan.py`
  - `app/routers/tools.py` — 练习工具路由
  - `app/services/llm.py` — `chat_completion()` LLM 调用
  - `app/services/rag.py` — `search()` RAG 检索
  - `app/services/quiz_generator.py` — 练习生成服务
  - `app/templates/` — 需新建 `study_plan.html`
  - `app/models/__init__.py` — 导出 StudyPlan
  - `app/templates/course_detail.html` — 增加"学习计划"入口
  - `app/main.py` — 注册新页面路由
- **已有工具**:
  - `GET /api/quiz/stats/{course_id}` — 按知识点统计正确率
  - `GET /api/wrong-book/{course_id}` — 错题列表
  - `GET /api/quiz/history/{course_id}` — 答题历史
  - `POST /api/wrong-book/redo/{course_id}` — 错题巩固练习生成

## 实现任务

### 1. [模型] 创建学习计划数据模型

新建 `app/models/study_plan.py`：

```python
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class StudyPlan(Base):
    __tablename__ = "study_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)
    plan_json = Column(Text, nullable=False)  # JSON: 每日计划列表
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student = relationship("User", backref="study_plans")
    course = relationship("Course", backref="study_plans")

class StudyPlanItem(Base):
    __tablename__ = "study_plan_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("study_plans.id"), nullable=False, index=True)
    day = Column(Integer, nullable=False)  # 第几天（1-based）
    knowledge_point = Column(String(200), nullable=False)
    task_type = Column(String(50), nullable=False)  # review / quiz / chat_practice
    description = Column(Text, nullable=False)
    is_completed = Column(Integer, default=0)
    completed_at = Column(DateTime, nullable=True)

    plan = relationship("StudyPlan", backref="items")
```

在 `app/models/__init__.py` 中添加导入。

### 2. [后端] 生成学习计划 API

在 `app/routers/tools.py` 中新增：

```python
@router.post("/api/study-plan/generate/{course_id}")
async def generate_study_plan(
    course_id: int,
    days: int = Form(7),  # 计划天数，默认 7 天
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    1. 获取学生统计：stats + wrong_book + history
    2. 调用 RAG 获取课程知识点概览
    3. 构建 LLM prompt，包含：
       - 薄弱知识点列表（<60% 正确率）
       - 错题知识点列表
       - 课程知识点概览（来自 RAG）
       - 课程名称
    4. 调用 LLM 生成每日学习计划 JSON
    5. 保存 StudyPlan + StudyPlanItem 到数据库
    6. 返回计划摘要
    """
```

LLM Prompt 示例：
```
你是一个AI学习规划师。请为以下学生生成一份为期{days}天的学习计划。

课程: {course_name}
该学生在以下知识点上表现薄弱: {weak_points}
错题涉及: {wrong_point_topics}
课程覆盖的知识点: {kb_topics}

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
- task_type 可选: review(知识点复习), quiz(练习题), chat_practice(与AI同学讨论)
```

```python
@router.get("/api/study-plan/{course_id}")
async def get_study_plan(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """获取最新学习计划（含完成状态）"""
```

```python
@router.post("/api/study-plan/item/{item_id}/complete")
async def complete_plan_item(
    item_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """标记计划项为已完成"""
```

```python
@router.post("/api/study-plan/{plan_id}/regenerate")
async def regenerate_study_plan(
    plan_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """基于已完成的项重新生成后续计划"""
```

### 3. [后端] AI 每日推荐（轻量版）

可选功能：不生成完整 7 天计划，而是每次生成当天的 3 项推荐。

```python
@router.get("/api/study-plan/daily-recommend/{course_id}")
async def get_daily_recommend(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """轻量版：每次返回当天的 3 条学习推荐"""
```

### 4. [前端] 学习计划页面

新建 `app/templates/study_plan.html`，继承 `base.html`：

**头部**：
- 课程名称 + "AI 学习计划"标题
- "生成计划"按钮（AI 生成，带 loading spinner）
- 最近计划生成时间
- "重新生成"按钮

**计划卡片区**：
- 按天 tabs（第 1 天 / 第 2 天 / ...）
- 每天显示任务列表，每个任务：
  - 左侧：checkbox（完成后可勾选）
  - 中间：知识点名称标签 + 任务类型 badge（复习/练习/讨论）
  - 右侧：任务描述
  - 已完成项：灰色+删除线

**进度概览**：
- 顶部进度条显示整体完成百分比
- "已完成 X/Y 项"

**生成过程**：
- 点击"生成计划"后显示等待动画
- LLM 生成可能需要几秒，显示"AI 正在分析你的学习数据……"
- 生成完成后自动渲染计划

注册路由到 `app/main.py`:

```python
@app.get("/study-plan/{course_id}")
async def study_plan_page(
    request: Request,
    course_id: int,
    user: User = Depends(require_user),
):
    return render_template("study_plan.html", request=request, user=user, course_id=course_id)
```

### 5. [前端] 集成入口

- `course_detail.html` 的工具 tab 或导航栏增加"学习计划"链接 → `/study-plan/{course_id}`
- `dashboard.html` 的课程卡片增加"学习计划"按钮（学生可见）

## 验收标准

- [ ] 点击"生成计划"后 AI 正确分析薄弱知识点并生成每日计划
- [ ] 每日计划 tabs 切换正常，显示对应日期的任务列表
- [ ] checkbox 勾选后可标记完成，进度条实时更新
- [ ] 重新生成功能正常工作
- [ ] 学习数据不足时给出友好提示
- [ ] 页面风格与现有主题一致
- [ ] 无导入错误，app 正常启动

## 参考代码模式

- LLM Prompt 工程参考 `app/services/quiz_generator.py` 中的 prompt 构建方式
- RAG 检索参考 `app/services/rag.py` 的 `search()` 函数获取课程知识点概览
- 统计接口参考 `app/routers/tools.py` 中 `GET /api/quiz/stats/{course_id}`
- 前端 tabs 模式参考 `app/templates/course_detail.html` 的 Bootstrap tabs 实现
- 数据库分页/排序参考现有 SQLAlchemy query 模式
