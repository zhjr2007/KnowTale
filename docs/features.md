# 知喻（KnowTale）功能目标与开发规划

> 广州大学第二届"庆园杯"人工智能创新应用大赛 · 主赛道 · 主题三 参赛作品

---

## 项目定位

知喻是一个**多智能体协同课后学习平台**，核心理念是"知识AI化，价值真人化"——AI 承接标准化知识传递与基础答疑，真人教师回归经验传递与价值引导。

## 技术架构

```
┌─ Docker Compose ──────────────────────────────────────────┐
│  FastAPI App（Python 全栈）                                │
│    ├── 认证系统（JWT 双角色权限）                           │
│    ├── 课程管理（创建/选课/群聊）                           │
│    ├── 知识库（MinerU→百炼Embedding→ChromaDB→百炼Rerank）  │
│    ├── AI角色引擎（教师/学生分角色自动生成）                 │
│    ├── 学习工具（题库/错题本/抽背/思维导图）                │
│    └── 学情分析（对话采集→动态迭代→PDF报告）               │
│                                                             │
│  ChromaDB（向量库）                                         │
│  MinerU（GPU文档解析）                                      │
└─────────────────────────────────────────────────────────────┘
```

## 六大模块与完成状态

| 模块 | 功能 | 状态 |
|------|------|------|
| **① 双角色账号** | 教师/学生注册登录，JWT 权限校验 | ✅ 已完成 |
| **② 课程 RAG 知识库** | MinerU 文档解析 → 百炼 Embedding → ChromaDB 存储 → 百炼 Rerank 精排 | ✅ 已完成 |
| **③ 分层 AI 角色** | AI 教师自动生成 + 三类 AI 学生 + AI 学长/学姐 | ✅ 已完成 |
| **④ 应试学习工具** | 题库生成、自动判分、错题本、知识点抽背、思维导图 | ⬅️ **当前目标** |
| **⑤ 学情动态迭代** | 对话采集、周报生成、角色 prompt 自动更新 | 🔜 后续 |
| **⑥ 前端定制** | 蓝白教育主题、群聊界面、功能裁剪 | 🔜 后续 |

---

## 模块④：应试学习工具集 详细规划

### 4.1 题库生成（Quiz Generation）

**流程**：
1. 教师选择课程 → 系统从知识库提取知识点
2. 调用百炼 Qwen 模型，按章节/难度生成选择题和简答题
3. 题目以 JSON 格式存储，每道题关联知识点标签

**API 接口**：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/quiz/generate/{course_id}` | 生成一套练习题 |
| GET | `/api/quiz/list/{course_id}` | 列出课程所有练习 |
| GET | `/api/quiz/{quiz_id}` | 获取练习详情（含题目） |
| POST | `/api/quiz/{quiz_id}/submit` | 提交答案 |
| GET | `/api/quiz/{quiz_id}/result/{attempt_id}` | 查看判分结果 |

### 4.2 自动判分（Auto Grading）

- **选择题**：直接比对答案，即时出分
- **简答题**：调用百炼 Qwen 模型，根据参考答案判断正误并给出评价
- 每道题自动记录到错题本

### 4.3 错题本（Wrong Answer Book）

**API 接口**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/wrong-book/{course_id}` | 查看该课程错题 |
| DELETE | `/api/wrong-book/{id}` | 移除单条错题 |
| POST | `/api/wrong-book/review` | 选错题生成专项练习 |

### 4.4 知识点抽背（Knowledge Review）

**流程**：
1. 从知识库或错题本中随机抽取知识点
2. 以问答形式展示，学生作答后显示正确答案和解析
3. 支持"下一题"、"标记已掌握"等操作

**API 接口**：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/review/start/{course_id}` | 开始抽背会话 |
| GET | `/api/review/{session_id}/next` | 下一题 |
| POST | `/api/review/{session_id}/answer` | 提交答案 |

### 4.5 思维导图（Mind Map）

**流程**：
1. 从课程知识库提取章节结构
2. 调用百炼 Qwen 分析章节间的层级关系
3. 生成 Markdown 格式的层级结构（可用 Markmap 等工具渲染）

**API 接口**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/mindmap/{course_id}` | 获取思维导图 Markdown |

---

## 数据模型

```
Quiz（练习）
├── id, course_id, title, question_count
├── Question（题目）
│   ├── id, quiz_id, content, type(choice|short_answer)
│   ├── options（JSON, 选择题选项）
│   ├── correct_answer, knowledge_point
├── QuizAttempt（答题记录）
│   ├── id, quiz_id, student_id, score, total, completed_at
├── Answer（单题回答）
│   ├── id, attempt_id, question_id, student_answer, is_correct
WrongBookRecord（错题本）
  ├── id, student_id, course_id, question_content
  ├── correct_answer, student_answer, knowledge_point
```

---

## 进度时间线

| 时间 | 目标 |
|------|------|
| 7月11日-12日 | ✅ 项目骨架 + 认证 + 课程管理 |
| 7月12日-13日 | ✅ RAG 知识库 + MinerU + 百炼API + AI角色引擎 |
| **7月13日-14日** | **⬅️ 学习工具集（题库/错题本/抽背/思维导图）** |
| 7月15日-16日 | 多智能体群聊对话系统 |
| 7月17日-18日 | 学情分析 + PDF 报告 |
| 7月19日-20日 | UI 打磨 + 文档 + 演示准备 |
| 7月21日-9月15日 | 迭代优化 + 提交材料 |
