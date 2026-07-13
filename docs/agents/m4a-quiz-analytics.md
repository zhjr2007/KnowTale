# M4a: 练习统计图表 & 错题本间隔重复

## 目标

为练习模块增加可视化统计图表（Chart.js），实现错题本的间隔重复复习功能（SuperMemo SM-2 简化版），并支持导出错题 PDF。

## 技术上下文

- **项目根目录**: `D:\KnowTale`
- **相关文件**:
  - `app/routers/tools.py` — 练习和错题本路由
  - `app/services/quiz_generator.py` — 练习生成服务
  - `app/models/quiz.py` — Quiz, Question, QuizAttempt, Answer, WrongBookRecord
  - `app/templates/quiz_list.html` — 练习列表页
  - `app/templates/quiz.html` — 答题页面
  - `app/templates/quiz_result.html` — 答题结果页
  - `app/templates/wrong_book.html` — 错题本页
  - `app/static/css/style.css` — 全局样式
- **已有功能**:
  - `GET /api/quiz/list/{course_id}` — 练习列表含最佳成绩
  - `GET /api/quiz/{quiz_id}` — 获取题目
  - `POST /api/quiz/{quiz_id}/submit` — 提交批改
  - `GET /api/wrong-book/{course_id}` — 错题列表
  - `POST /api/wrong-book/redo/{course_id}` — 错题巩固练习生成
  - `GET /api/quiz/stats/{course_id}` — 按知识点统计
  - `GET /api/quiz/history/{course_id}` — 答题历史
- **数据关系**: WrongBookRecord（student_id, course_id, question_content, correct_answer, student_answer, knowledge_point, question_type, source_quiz_id, created_at）

## 实现任务

### 1. [后端] 扩展统计接口

在 `app/routers/tools.py` 中新增或扩展现有 `GET /api/quiz/stats/{course_id}`：

```python
@router.get("/api/quiz/stats/{course_id}")
async def get_quiz_stats(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """返回增强版统计数据"""
```

返回格式：
```json
{
  "by_knowledge_point": [{"name": "知识点A", "total": 10, "correct": 7, "percentage": 70}, ...],
  "by_difficulty": [{"difficulty": "easy", "total": 5, "correct": 4}, ...],
  "weekly_trend": [{"week": "2026-W28", "score_avg": 75, "attempts": 8}, ...],
  "total_quizzes": 12,
  "total_attempts": 35,
  "overall_percentage": 72.5,
  "weakest_points": ["知识点B", "知识点C"],
}
```

- `by_knowledge_point`: 聚合学生所有答题记录，按 knowledge_point 分组，计算正确率
- `by_difficulty`: 按 easy/medium/hard 分组
- `weekly_trend`: 按 ISO 周编号聚合最近 8 周数据（仅该学生对应该课程的数据）
- `weakest_points`: 取正确率最低的 3 个知识点（如果有数据）

注意：区分学生和教师视角。学生只看到自己的数据，教师看到全班汇总数据（需遍历课程下所有学生的数据）。

### 2. [模型] 错题本增加复习字段

在 `app/models/quiz.py` 的 `WrongBookRecord` 类中添加：

```python
review_count = Column(Integer, default=0)         # 已复习次数
next_review_date = Column(Date, nullable=True)     # 下次复习日期
last_review_at = Column(DateTime, nullable=True)   # 上次复习时间
```

执行 `init_db()` 后新增字段需手动 ALTER TABLE 或删除旧 db 文件重来（开发阶段可接受删除 `data/knowtale.db`）。

### 3. [后端] 间隔重复复习 API

在 `app/routers/tools.py` 中新增：

```python
@router.get("/api/wrong-book/review-today/{course_id}")
async def get_todays_review(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    返回今天需要复习的错题（next_review_date <= today）
    按 next_review_date ASC 排序，最多 10 条
    """
```

```python
@router.post("/api/wrong-book/review/{record_id}")
async def review_wrong_record(
    record_id: int,
    is_correct: bool = Form(...),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    复习错题后更新间隔重复参数。
    使用简化版 SM-2 算法：
      - 如果答对: review_count += 1; 间隔天数 = min(2^(review_count), 30)
      - 如果答错: review_count = 0; 间隔天数 = 1
      - next_review_date = today + 间隔天数
    """
```

### 4. [前端] 统计图表页面

修改或扩展 `app/templates/quiz_list.html`（或新建 `quiz_stats.html`）：

**知识点掌握情况** — 水平柱状图：
- X 轴：知识点名称
- Y 轴：正确率百分比
- 颜色：绿色（≥80%）、黄色（60-79%）、红色（<60%）
- 使用 Chart.js CDN

**难度分布** — 饼图或环形图：
- easy / medium / hard 的正确率对比
- 每个扇形显示正确数/总数

**周趋势** — 折线图：
- X 轴：周数
- Y 轴：平均正确率
- 双线：准确率和做题数（双 Y 轴或叠图）

**知识点薄弱项** — 红色高亮列表

页面入口：
- `quiz_list.html` 顶部增加"统计"按钮，点击切换到统计视图
- 或者新增 tab 切换（练习列表 / 统计）

### 5. [前端] 错题本间隔重复界面

修改 `app/templates/wrong_book.html`：

- 现有错题列表保持不变
- 顶部增加"今日复习"区域：
  - 显示"今日还需复习 N 题"
  - 点击开始复习，逐题展示（翻转卡片效果）
  - 先显示题目，用户思考后点击"显示答案"
  - 然后选择"答对了"或"答错了"
  - 选择后 AJAX 调用复习 API，自动更新下次复习日期
  - 全部完成后显示"今日复习完成！"

**卡片翻转效果**（纯 CSS）：
```css
.flip-card { perspective: 1000px; }
.flip-card-inner { transition: transform 0.6s; transform-style: preserve-3d; }
.flip-card.flipped .flip-card-inner { transform: rotateY(180deg); }
```

### 6. [前端] 导出错题 PDF

在 `wrong_book.html` 中增加"导出 PDF"按钮：

- 使用 `window.print()` 简单实现
- 或者引入 `html2canvas` + `jsPDF` CDN 实现更精美的 PDF
- 打印/导出时只包含错题内容（隐藏导航栏、按钮等无关元素）
- 添加 `@media print` CSS 样式

```css
@media print {
    nav, .btn, .no-print { display: none !important; }
    body { font-size: 12pt; }
}
```

## 验收标准

- [ ] 统计图表页面正常显示（柱状图 + 饼图 + 折线图）
- [ ] 知识点掌握柱状图正确反映学生各知识点正确率
- [ ] 周趋势折线图显示最近 8 周数据
- [ ] 薄弱知识点红色高亮
- [ ] 错题本"今日复习"功能正常，间隔重复算法正确更新
- [ ] 卡片翻转动画流畅
- [ ] PDF 导出功能正常，打印视图友好
- [ ] 前后端接口数据一致
- [ ] 无导入错误，app 正常启动

## 参考代码模式

- Chart.js 用法: `<canvas id="myChart"></canvas>` + `new Chart(ctx, {type: 'bar', data: {...}})`
- CDN: `<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>`
- 统计接口参考 `app/routers/tools.py` 中已有 `GET /api/quiz/stats/{course_id}` 的实现
- 错题本接口参考 `app/routers/tools.py` 中 `WrongBookRecord` 的 CRUD 操作模式
- 数据库查询聚合: SQLAlchemy `func.count()`, `func.avg()`, `group_by()` 等
- 日期处理: Python `datetime` + `timedelta` 计算复习间隔
