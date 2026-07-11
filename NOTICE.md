# NOTICE

## 知喻（KnowTale）多智能体协同课后学习平台

本项目为 **广州大学第二届"庆园杯"人工智能创新应用大赛** 参赛作品。

### 开源组件与许可声明

本项目基于以下开源项目二次开发，保留原项目全部版权声明与许可条款：

| 项目 | 用途 | 许可证 |
|------|------|--------|
| [SillyTavern](https://github.com/SillyTavern/SillyTavern) | 多角色对话核心引擎 | AGPL-3.0 |
| [MinerU](https://github.com/opendatalab/MinerU) | 文档预处理引擎 | Apache-2.0 (自定义许可) |
| [Chroma](https://github.com/chroma-core/chroma) | 向量数据库 | Apache-2.0 |
| [BGE-M3](https://github.com/FlagOpen/FlagEmbedding) | 向量嵌入模型 | MIT |
| [BGE-Reranker-v2](https://github.com/FlagOpen/FlagEmbedding) | 重排模型 | MIT |

### 版权与合规说明

- 本项目整体采用 **AGPL-3.0** 协议（与 SillyTavern 底座一致）
- 所有原创增量代码存放于 `/edu-modules` 目录
- 所有新增插件存放于 `/public/plugins/edu-*` 目录
- 第三方开源组件存放于 `/third-party` 目录，保留各自原始 LICENSE 文件
- SillyTavern 原生核心代码保留原目录结构，未做大规模重构
- 修改过的原生代码文件头部均已添加修改说明注释

### 原创工作量声明

以下模块为本次参赛的原创开发内容：
1. 双角色账号权限体系 (`/edu-modules/account`)
2. 教育场景增强型 RAG 知识库系统 (`/edu-modules/rag`)
3. 分层 AI 角色自动生成引擎 (`/edu-modules/role-generator`)
4. 学情驱动的动态角色迭代机制 (`/edu-modules/analysis`)
5. 应试学习工具集 (`/edu-modules/learning-tools`)
6. 前端定制化重构与教育场景改造 (`/public/plugins/edu-*`)

### 联系方式

- 项目仓库：https://github.com/zhjr2007/KnowTale
- 大赛官网：https://aihome.gzhu.edu.cn
