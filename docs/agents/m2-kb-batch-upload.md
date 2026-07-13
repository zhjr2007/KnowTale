# M2: 知识库批量上传 & 文件预览增强

## 目标

为文档知识库模块增强批量上传、拖拽上传、上传进度显示、文件内容预览功能，提升教师上传课程资料的使用体验。

## 技术上下文

- **项目根目录**: `D:\KnowTale`
- **相关文件**:
  - `app/routers/knowledge.py` — 知识库路由
  - `app/services/document_parser.py` — 文档解析服务
  - `app/services/rag.py` — 向量索引服务
  - `app/templates/knowledge.html` — 知识库管理页面
  - `app/__init__.py` — 应用初始化
- **已有接口**:
  - `POST /api/knowledge/upload/{course_id}` — 单文件上传+解析+索引
  - `POST /api/knowledge/preview/{course_id}` — 上传+解析（不索引）+ 返回预览文本
  - `POST /api/knowledge/confirm/{course_id}` — 确认预览文件并索引
  - `GET /api/knowledge/documents/{course_id}` — 已索引文档列表
  - `DELETE /api/knowledge/documents/{course_id}/{doc_id}` — 删除文档
- **支持格式**: pdf, docx, doc, pptx, ppt, txt, md
- **前端现有模式**: Bootstrap 5 + fetch API + AJAX 模态框
- **设计风格**: 蓝白校园主题（参考 `static/css/style.css`）

## 实现任务

### 1. [前端] 拖拽上传区域

改造 `knowledge.html` 中的上传模态框或新增上传区域：

- 在文件列表上方新建一个拖拽区域（dashed border 方框）
- 支持拖拽文件到区域（监听 `dragover`, `drop` 事件）
- 拖入时触发文件上传（直接开始上传，无需额外确认步骤）
- 也可以点击区域弹出文件选择框
- 支持多文件选择（`multiple` 属性）
- 拖拽区域显示提示文字："拖拽文件到此处上传，或点击选择文件（支持 PDF/Word/PPT/TXT/MD）"
- 拖拽悬停时区域高亮（border 变色 + 背景色变化）

```html
<!-- 拖拽区域结构 -->
<div id="drop-zone" class="border-2 border-dashed rounded p-5 text-center"
     style="border: 2px dashed #ccc; cursor: pointer;">
  <i class="bi bi-cloud-upload fs-1 text-primary"></i>
  <p class="mt-2 text-muted">拖拽文件到此处上传</p>
  <p class="text-muted small">或点击选择文件</p>
  <input type="file" id="file-input" multiple hidden accept=".pdf,.docx,.doc,.pptx,.ppt,.txt,.md">
</div>
```

### 2. [前端] 多文件上传队列 & 进度条

- 选择/拖入文件后，在上传区域下方显示上传队列列表
- 每个文件显示：文件名 + 文件大小 + 上传进度条（Bootstrap Progress Bar）+ 状态（等待中/上传中/解析中/完成/失败）
- 使用 XMLHttpRequest 实现上传进度监听（`xhr.upload.onprogress`）
- 每个文件独立异步上传（可并行 3 个，避免浏览器连接数过多）
- 上传完成后自动更新文档列表
- 失败时红色提示 + 可点击重试

```javascript
// 上传单个文件，带进度
function uploadFile(file, courseId) {
    const formData = new FormData();
    formData.append('file', file);
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `/api/knowledge/upload/${courseId}`);
    xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 100);
            // 更新对应文件的进度条
        }
    };
    xhr.onload = () => { /* 上传完成，刷新列表 */ };
    xhr.onerror = () => { /* 标记失败 */ };
    xhr.send(formData);
}
```

### 3. [后端] 批量上传支持

修改 `app/routers/knowledge.py` 中的上传逻辑，当前已是单文件 UploadFile，无需改动后端。
主要改造在前端发送多个请求。

### 4. [前端] 文件内容预览

在文件列表每行末尾增加"预览"按钮（仅在解析完成后可点击）：

- 点击后查询预览数据
- 模态框展示文件内容前 2000 字（纯文本）
- 对 PDF 文件尝试展示前 3 页文本
- 预览模态框可滚动，底部显示"共 x 字符"
- 关闭

需要新增后端接口或在已有 `/api/knowledge/preview/{course_id}` 基础上扩展：

```python
@router.get("/api/knowledge/preview-file/{course_id}/{doc_id}")
async def preview_document(
    course_id: int,
    doc_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
```
- 读取 `knowledge_documents.file_path` 对应文件
- 如果是文本类文件（txt/md），直接返回前 2000 字
- 如果是 PDF/Word/PPT，调用 `document_parser.parse_document()` 解析后返回前 2000 字
- 响应：`{"filename": str, "preview_text": str, "total_chars": int, "file_type": str}`

### 5. [前端] 文件类型图标美化

在文件列表中，根据 `file_type` 显示对应图标：

- pdf → `<i class="bi bi-filetype-pdf text-danger"></i>`
- doc/docx → `<i class="bi bi-filetype-docx text-primary"></i>`
- ppt/pptx → `<i class="bi bi-filetype-pptx text-warning"></i>`
- txt → `<i class="bi bi-filetype-txt text-secondary"></i>`
- md → `<i class="bi bi-filetype-md text-info"></i>`

## 验收标准

- [ ] 拖拽文件到上传区域自动触发上传
- [ ] 点击上传区域可选择多个文件
- [ ] 上传队列显示进度条（每个文件独立）
- [ ] 上传完成后文档列表自动刷新
- [ ] 文件预览模态框可查看文本内容前 2000 字
- [ ] 文件列表显示对应类型图标
- [ ] 上传失败可重试
- [ ] 页面风格与现有蓝白主题一致

## 参考代码模式

- XHR 上传进度：`xhr.upload.onprogress` 事件
- 拖拽事件：`dragenter` / `dragover` / `drop` / `dragleave` 四个事件处理
- 预览接口：参考 `app/routers/knowledge.py` 中已有的 preview 路由实现
- 页面样式：参考 `static/css/style.css` 中的卡片和按钮样式
