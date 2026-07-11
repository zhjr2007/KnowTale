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
├── edu-modules/              # 原创业务模块
│   ├── account/              # 双角色账号权限体系
│   ├── rag/                  # 教育场景增强型 RAG 知识库
│   ├── role-generator/       # 分层 AI 角色自动生成引擎
│   ├── learning-tools/       # 应试学习工具集
│   └── analysis/             # 学情分析与动态角色迭代
├── public/plugins/           # 前端插件
│   ├── edu-account/          # 账号管理插件
│   ├── edu-rag/              # 知识库管理插件
│   └── edu-learning-tools/   # 学习工具插件
├── third-party/              # 第三方开源组件
├── NOTICE.md                 # 开源合规声明
├── .env.example              # 环境配置模板
└── README.md
```

## 技术栈

| 组件 | 用途 |
|------|------|
| SillyTavern | 多角色对话引擎（AGPL-3.0） |
| MinerU | 文档预处理解析 |
| bge-m3 + bge-reranker-v2 | 向量嵌入与重排 |
| Chroma | 向量数据库 |

## 快速开始

### 环境要求

- Node.js 18+
- Python 3.10+
- Chroma 向量数据库
- （可选）MinerU 文档解析服务 / NVIDIA GPU

### 安装与启动

```bash
# 1. 克隆项目
git clone https://github.com/zhjr2007/KnowTale.git
cd KnowTale

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API 密钥等配置

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动服务
python server.py
```

详细部署步骤请参考 [部署手册](docs/deploy-guide.md)。

## 核心功能

1. **双角色账号体系** — 教师/学生权限分离，数据隔离
2. **教育 RAG 知识库** — 高精度课件解析与检索
3. **分层 AI 角色** — 一键生成教师+三类学生角色
4. **学情动态迭代** — 对话驱动的角色自动优化
5. **备考工具集** — 题库、错题本、抽背、思维导图

## 开源合规

本项目基于 SillyTavern（AGPL-3.0）、MinerU（Apache-2.0）等开源项目二次开发。完整合规声明见 [NOTICE.md](NOTICE.md)。整体项目采用 AGPL-3.0 协议。

## 参赛信息

- **赛事**：广州大学第二届"庆园杯"人工智能创新应用大赛
- **赛道**：主赛道 · 主题三 开放创新探索
- **团队**：知喻 KnowTale
- **提交截止**：2026 年 9 月 15 日
