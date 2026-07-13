# M6a: 全局 UI/UX 打磨

## 目标

全面提升应用的用户体验和视觉品质：添加页面过渡动画、骨架屏加载、统一 Toast 通知系统、响应式布局优化、初始暗色模式支持。

## 技术上下文

- **项目根目录**: `D:\KnowTale`
- **相关文件**:
  - `app/templates/base.html` — 全局布局模板（导航栏、JS 引入）
  - `app/templates/*.html` — 所有 15 个模板
  - `static/css/style.css` — 现有蓝白主题样式
  - `static/js/` — 需新建 `app.js`（全局 JS）
- **现有设计**:
  - Bootstrap 5 + Bootstrap Icons（CDN）
  - 蓝白主题: primary `#1a56db`, bg `#f8fafc`, light blue `#f0f4ff`
  - 卡片阴影: `box-shadow: 0 2px 8px rgba(0,0,0,0.06)`
  - 导航栏渐变: `linear-gradient(135deg, #1a56db, #2563eb)`
- **纯前端任务**：不涉及后端逻辑修改

## 实现任务

### 1. [前端] 全局 Toast 通知系统

在 `app/templates/base.html` 中添加 Toast 容器和 JS 工具函数：

```html
<!-- Toast 容器（固定在右下角） -->
<div class="toast-container position-fixed bottom-0 end-0 p-3" id="toastContainer"
     style="z-index: 9999;"></div>

<script>
// 全局 Toast 函数
function showToast(message, type = 'success', duration = 3000) {
    const icons = { success: 'bi-check-circle-fill', danger: 'bi-x-circle-fill', warning: 'bi-exclamation-triangle-fill', info: 'bi-info-circle-fill' };
    const html = `
        <div class="toast align-items-center text-bg-${type} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body"><i class="bi ${icons[type]} me-2"></i>${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>`;
    const container = document.getElementById('toastContainer');
    container.insertAdjacentHTML('beforeend', html);
    const toastEl = container.lastElementChild;
    const toast = new bootstrap.Toast(toastEl, { delay: duration });
    toast.show();
    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
}
</script>
```

**替换所有现有页面中的 alert/通知代码**：遍历所有模板 `.html` 文件，将分散的 alert 弹窗、确认框、成功提示等统一替换为调用 `showToast()`。注意不要删除确认对话框（`confirm()`），只需替换成功/错误消息提示。

### 2. [前端] 骨架屏加载

在 `app/templates/base.html` 中添加骨架屏 CSS，在数据加载中的页面使用：

```css
/* 骨架屏 CSS */
.skeleton {
    background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
    background-size: 200% 100%;
    animation: skeleton-loading 1.5s infinite;
    border-radius: 4px;
}
@keyframes skeleton-loading {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}
```

**应用骨架屏的页面**：
1. `dashboard.html` — 课程列表加载时显示 6 个骨架卡片（3x2 网格）
2. `quiz_list.html` — 练习列表加载时显示 4 个骨架行
3. `analytics.html` — 图表加载时显示圆形和柱状骨架
4. `knowledge.html` — 文档列表加载时显示 3 个骨架行

实现方式：在 HTML 中放置骨架屏占位元素，AJAX 数据加载完成后 `display:none` 隐藏骨架屏，显示真实内容。

```html
<!-- 示例：课程列表骨架屏 -->
<div id="skeleton-courses" class="row g-4">
    <div class="col-md-4" * 6>
        <div class="card shadow-sm border-0" style="height: 200px;">
            <div class="card-body">
                <div class="skeleton" style="height: 24px; width: 70%; margin-bottom: 12px;"></div>
                <div class="skeleton" style="height: 16px; width: 90%; margin-bottom: 8px;"></div>
                <div class="skeleton" style="height: 16px; width: 60%;"></div>
            </div>
        </div>
    </div>
</div>
```

### 3. [前端] 页面切换动画

在 `app/templates/base.html` 中添加 fade-in 动画：

```css
.page-transition {
    animation: fadeIn 0.3s ease-in-out;
}
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}
```

在每个页面的 `<main>` 或 `<div class="container">` 上添加 `class="page-transition"`。

### 4. [前端] 响应式布局优化

检查并修复所有模板的 Bootstrap 响应式问题：

1. `dashboard.html` 课程网格：
   - `col-md-4 col-lg-3`（桌面 3-4 列）
   - `col-sm-6`（平板 2 列）
   - `col-12`（手机 1 列）

2. `course_detail.html` tabs：
   - 手机端 tabs 可左右滑动（`overflow-x: auto` + `flex-wrap: nowrap`）
   - tab 内容区域手机端 padding 减少

3. `analytics.html` 图表：
   - 大屏：图表并排 2 列
   - 小屏：图表堆叠 1 列

4. 表格类页面（knowledge, quiz_list, wrong_book）：
   - 大屏：表格展示
   - 小屏：卡片列表展示
   - 使用 Bootstrap 的 `table-responsive` 类

5. `base.html` 导航栏：
   - 手机端折叠：品牌名左侧，汉堡菜单右侧
   - 折叠菜单可滚动

### 5. [前端] 按钮加载状态

为所有提交/保存/生成类按钮添加加载状态：

```javascript
function setLoading(btn, loading = true) {
    if (loading) {
        btn.disabled = true;
        btn.dataset.originalHtml = btn.innerHTML;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>处理中...';
    } else {
        btn.disabled = false;
        btn.innerHTML = btn.dataset.originalHtml || btn.innerHTML;
    }
}
```

需要修改的按钮：
- login/register 提交按钮
- 练习生成按钮
- 角色生成按钮
- 计划生成按钮
- 上传按钮

### 6. [前端] 暗色模式初始支持（CSS Variables）

在 `static/css/style.css` 中定义 CSS 变量：

```css
:root {
    --bg-primary: #f8fafc;
    --bg-card: #ffffff;
    --text-primary: #1e293b;
    --text-secondary: #64748b;
    --border-color: #e2e8f0;
    --card-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

[data-theme="dark"] {
    --bg-primary: #0f172a;
    --bg-card: #1e293b;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --border-color: #334155;
    --card-shadow: 0 2px 8px rgba(0,0,0,0.3);
}
```

在 `base.html` 中替换所有硬编码颜色为 CSS 变量引用。

在导航栏添加暗色模式切换按钮（太阳/月亮图标），使用 localStorage 保存偏好：

```javascript
function toggleDarkMode() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
}
// 初始化
const savedTheme = localStorage.getItem('theme') || 'light';
document.documentElement.setAttribute('data-theme', savedTheme);
```

注意：暗色模式为 "初始支持" —— 不需要完美覆盖所有页面，优先确保：
- 导航栏
- 卡片
- 表格
- 按钮
- 背景
在这些主要区域的色值正确切换即可。

## 验收标准

- [ ] 全局 Toast 通知统一可用，所有页面调用一致
- [ ] 骨架屏在数据加载时正确显示
- [ ] 页面切换有 fade-in 动画
- [ ] 手机端布局正常，无溢出或错位
- [ ] 提交类按钮有加载状态
- [ ] 暗色模式切换可用，主要区域色值正确
- [ ] 暗色模式偏好保存在 localStorage
- [ ] 所有改动与现有功能兼容，无 JS 错误

## 参考代码模式

- Bootstrap Toast 组件: `new bootstrap.Toast(el).show()`
- Bootstrap Spinner: `<span class="spinner-border spinner-border-sm"></span>`
- CSS 变量: `var(--bg-primary)` 替换硬编码颜色
- 暗色模式参考: https://getbootstrap.com/docs/5.3/customize/color-modes/#javascript
- 响应式 grid: Bootstrap 5 的 `col-*` 和 `table-responsive` 类
