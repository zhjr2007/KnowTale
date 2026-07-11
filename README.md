# 知喻（KnowTale）多智能体协同课后学习平台

> 广州大学第二届"庆园杯"人工智能创新应用大赛 · 主赛道 · 主题三 开放创新探索

---

## 项目理念

**知识AI化，价值真人化**

AI 全面承接标准化知识传递与基础答疑，真人教师从重复性事务中解放，回归经验分享、价值引导与学情把控的不可替代职能。

## 核心架构

```
真人教师 ──→ AI教师 ──→ 分层AI学生 ──→ 真人学生
    │            │            │              │
    └────────────┴──── 学情动态迭代 ────────┘
```

- **真人教师**：上传课程素材、把控知识边界、查看学情报告
- **AI教师**：基于课程知识库的标准化知识点讲解与答疑
- **AI学生群体**：分层角色模拟讨论氛围，降低提问门槛
- **真人学生**：参与讨论、使用备考工具

## 项目结构

```
KnowTale/
├── app/                     # FastAPI 主应用
│   ├── main.py              # 入口 + 路由
│   ├── config.py            # 环境配置
│   ├── database.py          # 异步数据库引擎
│   ├── dependencies.py      # JWT 认证 + 权限
│   ├── models/              # 数据模型
│   │   ├── user.py          # 用户（老师/学生）
│   │   └── course.py        # 课程 + 选课
│   ├── routers/             # API 路由
│   │   ├── auth.py          # 注册/登录/登出
│   │   └── courses.py       # 课程管理
│   └── templates/           # Jinja2 页面模板
│       ├── base.html        # 蓝白导航框架
│       ├── login.html       # 登录页
│       ├── register.html    # 注册页
│       ├── dashboard.html   # 课程列表
│       └── course_detail.html # 课程详情
├── static/                  # 静态资源
├── docs/                    # 交付文档
├── Dockerfile               # 容器化部署
├── docker-compose.yml       # App + ChromaDB
├── requirements.txt         # Python 依赖
├── .env.example             # 环境配置模板
└── NOTICE.md                # 开源合规声明
```

## 技术栈

| 组件 | 用途 |
|------|------|
| **FastAPI** | 异步 Python Web 框架 |
| **Jinja2 + Bootstrap 5** | 服务端渲染前端 |
| **SQLAlchemy + aiosqlite** | 异步 ORM + 数据库 |
| **DeepSeek API** | 大模型推理（OpenAI 兼容） |
| **ChromaDB** | 向量知识库 |
| **PyMuPDF** | 文档解析 |
| **Docker Compose** | 快速部署 |

## 快速开始

### 环境要求

- Python 3.11+
- Docker & Docker Compose（可选）

### 安装与启动

```bash
# 1. 克隆项目
git clone https://github.com/zhjr2007/KnowTale.git
cd KnowTale

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 DeepSeek API Key

# 3. 启动（二选一）
# 方式 A：Docker 部署（推荐）
docker compose up -d

# 方式 B：Python 直接运行
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000 即可使用。

详细部署步骤请参考 [部署手册](docs/deploy-guide.md)。

## 核心功能

1. **双角色账号体系** — 教师/学生权限分离，数据隔离
2. **教育 RAG 知识库** — 高精度课件解析与检索
3. **分层 AI 角色** — 一键生成教师+三类学生角色
4. **学情动态迭代** — 对话驱动的角色自动优化
5. **备考工具集** — 题库、错题本、抽背、思维导图

## 开源合规

本项目基于通用开源库自主开发，无核心依赖 AGPL-3.0 项目。完整合规声明见 [NOTICE.md](NOTICE.md)。本项目采用 **MIT License** 开源。

## 参赛信息

- **赛事**：广州大学第二届"庆园杯"人工智能创新应用大赛
- **赛道**：主赛道 · 主题三 开放创新探索
- **团队**：知喻 KnowTale
- **提交截止**：2026 年 9 月 15 日
