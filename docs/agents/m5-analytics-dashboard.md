# M5: 实时学情看板增强 & 个人学情报告

## 目标

为学情分析模块增加可视化图表（Chart.js 雷达图/折线图）、学生个人学情报告、PDF 导出功能，以及低参与度学生自动标记功能。

## 技术上下文

- **项目根目录**: `D:\KnowTale`
- **相关文件**:
  - `app/services/analytics.py` — 学情分析服务（已有）
  - `app/services/role_updater.py` — 角色更新服务（已有）
  - `app/routers/analytics.py` — 分析路由（已有）
  - `app/models/conversation.py` — Conversation, WeeklyReport 模型（已有）
  - `app/templates/analytics.html` — 分析看板页面（已有）
  - `app/models/quiz.py` — QuizAttempt, WrongBookRecord（已有）
  - `app/models/course.py` — Course + CourseEnrollment
  - `app/main.py` — 页面路由
- **已有功能**:
  - `GET /api/analytics/{course_id}` — 获取分析报告
  - `POST /api/analytics/{course_id}/trigger` — 触发报告生成
  - `POST /api/analytics/{course_id}/update-roles` — 触发角色更新
  - `GET /api/quiz/stats/{course_id}` — 按知识点统计
  - `GET /api/quiz/history/{course_id}` — 答题历史
- **数据关系**:
  - WeeklyReport: id, course_id, week_start, week_end, report_json(Text)
  - Conversation: course_id, speaker_type, speaker_id, content, knowledge_tag, created_at
  - CourseEnrollment: course_id, student_id, status

## 实现任务

### 1. [后端] 扩展分析 API

在 `app/routers/analytics.py` 中新增：

```python
@router.get("/api/analytics/{course_id}/student/{student_id}")
async def get_student_analytics(
    course_id: int,
    student_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取单个学生的学情报告。
    教师可查看任何学生，学生只能看自己。
    返回数据：
    - participation: { total_messages, active_days, last_active_at }
    - quiz: { total_attempts, avg_score, weak_points }
    - knowledge_radar: [{"point": "知识点A", "mastery": 75}, ...]
    - weekly_trend: [{"week": "2026-W28", "msg_count": 12, "quiz_avg": 70}, ...]
    - recommendations: str (AI 生成的个性化学习建议)
    """
```

```python
@router.get("/api/analytics/{course_id}/export")
async def export_analytics(
    course_id: int,
    format: str = "html",  # html / json
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    导出学情分析报告。
    - format=html: 返回一个完整 HTML 页面（适合打印/导出 PDF）
    - format=json: 返回原始 JSON 数据
    """
```

```python
@router.get("/api/analytics/{course_id}/low-participation")
async def get_low_participation_students(
    course_id: int,
    threshold_days: int = 7,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    """
    返回低参与度学生列表。
    low_participation 判定：
    - 最近 threshold_days 天内消息数 < 3
    - 或最近 threshold_days 天内无答题记录
    - 或从未登录过该课程
    返回每个学生的 id, username, display_name, last_active_at, message_count_7d, quiz_count_7d
    """
```

### 2. [后端] 扩展分析服务

在 `app/services/analytics.py` 中增强 `analyze_conversations()`：

```python
async def analyze_conversations(course_id: int, days: int = 7, db: AsyncSession):
    """
    已有功能：统计消息、知识标签、AI 比例。
    增强：
    - 增加按天趋势（每天的消息数量）
    - 增加按 speaker_type 的参与度分布
    - 增加知识点热力图（知识标签 + 时间维度）
    - 增加低参与度学生标记
    """
    # 增强返回格式
    return {
        "total_messages": ...,
        "student_count": ...,
        "ai_ratio": ...,
        "top_tags": [...],
        "weak_tags": [...],
        "trend": [{"date": "2026-07-01", "count": 15}, ...],  # 新增：按天趋势
        "participation_distribution": {"ai_teacher": 30, "ai_student": 45, "student": 25},  # 新增
        "low_participation_students": [...],  # 新增
        "analysis": "...",
        "suggestions": "...",
    }
```

### 3. [后端] 知识点掌握度雷达图数据

在 `app/services/analytics.py` 中新增函数：

```python
async def get_knowledge_radar(course_id: int, student_id: int, db: AsyncSession):
    """
    获取学生各知识点的掌握度（0-100）。
    数据来源：
    1. QuizAttempt + Answer: 各知识点的答题正确率
    2. Conversation: 各知识点的参与频率（作为参考加分）
    权重：quiz 占 70%，conversation 占 30%
    返回: [{"point": "知识点A", "mastery": 75}, ...]
    """
```

### 4. [前端] 学情看板图表增强

改造 `app/templates/analytics.html`：

**参与度趋势折线图**：
- X 轴：日期
- Y 轴：消息数量
- 多条线：总消息、AI 教师消息、AI 学生消息、学生消息

**AI 参与比例饼图/环形图**：
- 三块：AI 教师、AI 学生、真人学生
- 显示百分比

**知识点活动 TOP10 水平柱状图**：
- X 轴：知识点名称
- Y 轴：消息数或出现频率

**薄弱知识点高亮区域**：
- 红色卡片列表，每个显示知识点名称 + 建议

**参与度统计卡片**：
- 总消息数（大数字）
- 活跃学生数
- AI 参与率百分比（带图标）

### 5. [前端] 学生个人学情报告

在 `analytics.html` 中新增学生选择下拉框（教师视图）：
- 下拉框列出所有已入班学生
- 选择学生后切换到该学生个人视图
- 个人视图包含：
  - 雷达图：各知识点掌握度
  - 参与度卡片：消息数、活跃天数
  - 答题统计：平均分、答题次数
  - AI 学习建议文本框（来自 LLM）

新增个人视图的 API 调用逻辑：

```javascript
async function loadStudentAnalytics(studentId) {
    const res = await fetch(`/api/analytics/${courseId}/student/${studentId}`);
    const data = await res.json();
    // 渲染雷达图、统计卡片、建议文本
}
```

### 6. [前端] PDF 导出

在 `analytics.html` 顶部增加"导出报告"按钮：

- 当前视图（班级概览或个人）导出为 PDF
- 使用 `window.print()` 方法，配合 `@media print` CSS
- 打印时隐藏按钮、导航栏、下拉框等交互元素
- 打印样式优化：字体、颜色、布局

### 7. [前端] 低参与度学生提醒

在 `analytics.html` 中新增"低参与度学生"区域：

- 红色警告卡片标题："需要关注的学生"
- 列表显示：学生头像、昵称、最后活跃时间、最近 7 天消息数
- 点击学生可跳转到该学生的个人报告

## 验收标准

- [ ] 班级概览图表正常显示（趋势折线图 + AI 比例饼图 + 知识点柱状图）
- [ ] 教师可查看任意学生的个人学情报告
- [ ] 个人报告含雷达图（知识点掌握度）
- [ ] 个人报告含 AI 生成的学习建议
- [ ] 低参与度学生列表正确识别并显示
- [ ] 导出 PDF 功能正常，打印视图友好
- [ ] 学生只能看到自己的报告，教师可看到全班
- [ ] 所有图表与现有蓝白主题风格一致（Chart.js 主题色 `#1a56db`）
- [ ] 无导入错误，app 正常启动

## 参考代码模式

- Chart.js 雷达图: `type: 'radar'`，数据格式 `datasets[{data: [75, 60, 85, ...], label: '掌握度'}]`
- Chart.js 折线图: `type: 'line'`，多数据集显示多条线
- Chart.js 主题色统一: `#1a56db` primary, `#3b82f6` light blue, `#f59e0b` amber, `#10b981` green
- 分析服务参考 `app/services/analytics.py` 已有 `analyze_conversations()` 实现
- AI 建议生成：构建 LLM prompt 包含学生统计数据，调用 `llm.chat_completion()`
- 权限控制参考 `app/dependencies.py` 的 require_teacher / require_user
- 前端图表参考 `m4a-quiz-analytics.md` 中的 Chart.js 使用模式
