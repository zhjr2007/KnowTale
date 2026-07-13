# M1a: 用户资料管理 & 班级成员管理

## 目标

为用户模块补充资料编辑功能和班级成员管理能力，覆盖教师端管理学生和用户端修改个人信息。

## 技术上下文

- **项目根目录**: `D:\KnowTale`
- **相关文件**:
  - `app/models/user.py` — User 模型（已有 avatar, display_name 字段）
  - `app/routers/auth.py` — 已有 auth 路由逻辑
  - `app/routers/courses.py` — 已有课程路由
  - `app/dependencies.py` — require_user / require_teacher 守卫
  - `app/templates/dashboard.html` — 可加入"个人资料"入口
  - `app/templates/base.html` — 导航栏可加入"个人中心"入口
  - `static/css/style.css` — 全局样式，蓝白主题
  - `app/main.py` — 页面路由注册
- **数据模型**: User 表已有 `avatar(VARCHAR 500)`、`display_name(VARCHAR 100)` 字段
- **守卫模式**: `require_user`（登录学生/教师通用）、`require_teacher`（仅教师）
- **用户类型**: `user.role` = `"teacher"` 或 `"student"`

## 实现任务

### 1. [后端] 用户资料更新 API

在 `app/routers/auth.py` 中添加：

```python
@router.post("/api/user/profile/update")
async def update_profile(
    display_name: str = Form(None),
    avatar: UploadFile = File(None),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
```

- 接受可选字段：`display_name`（字符串）、`avatar`（图片文件，jpg/png，最大 2MB）
- 头像存储到 `uploads/avatars/{user_id}_{timestamp}.ext`
- 返回更新后的用户信息 JSON

### 2. [后端] 获取用户信息 API

```python
@router.get("/api/user/profile")
async def get_profile(
    user: User = Depends(require_user),
):
```

- 返回当前用户的完整信息（含 avatar 的完整 URL）

### 3. [后端] 班级成员管理 API（在 `app/routers/courses.py` 中添加）

```python
@router.get("/api/courses/{course_id}/members")
async def list_members(
    course_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
```
- 返回该课程下所有状态为 `approved` 的学生列表（含 User.id, username, display_name, avatar, enrolled_at）
- 仅课程教师可访问

```python
@router.delete("/api/courses/{course_id}/members/{student_id}")
async def remove_member(
    course_id: int,
    student_id: int,
    user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
```
- 将学生从课程中移除（删除 CourseEnrollment 记录）
- 仅课程教师可操作

```python
@router.post("/api/courses/{course_id}/leave")
async def leave_course(
    course_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
```
- 当前学生退出课程
- 仅 `role == "student"` 可调用

### 4. [前端] 个人资料页面

新建 `app/templates/profile.html`，继承 `base.html`：

- 显示当前头像（img 圆形裁剪）
- 编辑昵称 input
- 上传头像 input[type=file]（预览后显示，未保存时不提交）
- 保存按钮 → AJAX POST /api/user/profile/update
- 成功 Toast 提示
- 风格参考 dashboard.html 卡片样式

注册路由到 `app/main.py`:

```python
@app.get("/profile")
async def profile_page(
    request: Request,
    user: User = Depends(require_user),
):
    return render_template("profile.html", request=request, user=user)
```

### 5. [前端] 班级管理页面

在 `course_detail.html` 中新增 tab 或新建 `members.html` 嵌入课程详情：

- 表格显示学生成员（序号、头像、昵称、用户名、加入时间、操作）
- 教师可见"移除"按钮（确认弹窗）
- 学生可见"退出课程"按钮（确认弹窗）
- 移除/退出后 AJAX 刷新表格

### 6. [前端] 导航栏入口

- `base.html` 导航栏右侧用户区域增加"个人中心"下拉选项 → `/profile`

## 验收标准

- [ ] 用户可上传/修改头像和昵称
- [ ] 教师可在课程详情页查看成员列表
- [ ] 教师可移除学生成员
- [ ] 学生可主动退出课程
- [ ] 所有操作有 Toast 提示成功/失败
- [ ] 页面风格与现有蓝白主题一致
- [ ] 无导入错误，app 正常启动

## 参考代码模式

- 文件上传模式参考 `routers/knowledge.py` 中的 `UploadFile` 使用方式
- 守卫模式参考 `routers/courses.py` 中的 `require_teacher` + 课程所有权检查
- 错误返回格式参考 `routers/auth.py` 中的 `JSONResponse(status_code=400, content={"detail": "..."})`
- 前端 AJAX 代码参考 `templates/dashboard.html` 中的 fetch API 使用方式
