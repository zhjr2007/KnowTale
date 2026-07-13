# M1b: 通知系统

## 目标

实现应用内通知系统，包括入班审批通知、新练习发布通知、学情周报推送，以及通知列表查看和已读管理。

## 技术上下文

- **项目根目录**: `D:\KnowTale`
- **相关文件**:
  - `app/models/` — 需新建 `notification.py`
  - `app/routers/` — 需新建 `notifications.py`
  - `app/templates/` — 需新建 `notifications.html`
  - `app/models/__init__.py` — 需导出 Notification
  - `app/main.py` — 注册通知路由
  - `app/templates/base.html` — 导航栏添加通知铃铛图标
  - `app/routers/courses.py` — 审批入班处需插入通知
  - `app/routers/tools.py` — 生成练习处需插入通知
  - `app/services/analytics.py` — 生成学情报告处需插入通知
- **守卫模式**: `require_user`
- **已有通知触发点**: 入班审批 (`courses.py`)、练习生成 (`tools.py`)、学情报告生成 (`analytics.py`)

## 实现任务

### 1. [模型] 创建通知数据模型

新建 `app/models/notification.py`：

```python
class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(50), nullable=False)  # enrollment_approved, enrollment_rejected, quiz_published, weekly_report
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)
    is_read = Column(Integer, default=0, index=True)  # 0=unread, 1=read
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="notifications")
    course = relationship("Course", backref="notifications")
```

在 `app/models/__init__.py` 中添加从 `notification` 导入 `Notification`。

### 2. [后端] 通知 API 路由

新建 `app/routers/notifications.py`：

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import require_user
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
```

**接口清单**：

```python
@router.get("")
async def list_notifications(
    page: int = 1,
    page_size: int = 20,
    unread_only: bool = False,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
```
- 返回当前用户通知列表（按 created_at DESC）
- 支持分页和 unread_only 过滤
- 响应格式: `{"notifications": [...], "total": int, "unread_count": int, "page": int}`

```python
@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
```
- 标记单条通知为已读
- 仅通知拥有者可操作

```python
@router.post("/read-all")
async def mark_all_read(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
```
- 标记当前用户全部通知为已读
- 返回 `{"success": true, "updated_count": int}`

### 3. [后端] 插入通知触发点

在 `app/routers/courses.py` 的审批逻辑中插入：

- 入班审批通过时 → 通知学生（type: `enrollment_approved`）
- 入班审批拒绝时 → 通知学生（type: `enrollment_rejected`）

在 `app/routers/tools.py` 的生成练习逻辑中插入：

- 练习生成成功后 → 通知所有已入班学生（type: `quiz_published`）

在 `app/services/analytics.py` 的 `generate_report()` 中插入：

- 周报生成后 → 通知课程教师（type: `weekly_report`）

提示：在路由函数中通过 `db.add(Notification(...))` 插入，调用 `await db.commit()`。批量通知时可遍历学生列表。

### 4. [前端] 通知页面

新建 `app/templates/notifications.html`，继承 `base.html`：

- 顶部：标题"通知" + "全部已读"按钮
- 通知列表：卡片式，每条通知显示
  - 左侧：类型图标（根据 type 显示不同 Bootstrap Icon）
  - 中间：标题 + 内容 + 时间（相对时间如"3分钟前"）
  - 右侧：未读蓝色圆点指示
  - 点击通知：如果关联 course_id，跳转到对应课程页面
- 分页：加载更多按钮或无限滚动
- 空状态："暂无通知"

注册路由到 `app/main.py`:

```python
@app.get("/notifications")
async def notifications_page(
    request: Request,
    user: User = Depends(require_user),
):
    return render_template("notifications.html", request=request, user=user)
```

### 5. [前端] 导航栏通知铃铛

修改 `app/templates/base.html` 导航栏右侧：

- 铃铛图标（`<i class="bi bi-bell"></i>`）
- 右上角红色未读计数 badge（AJAX 定时刷新或页面加载时获取）
- 下拉菜单显示最近 5 条未读通知（快速预览）
- 底部"查看全部"链接 → `/notifications`
- 下拉菜单中点击单条快速标记已读

## 验收标准

- [ ] 入班审批通过/拒绝时学生收到通知
- [ ] 教师发布新练习时学生收到通知
- [ ] 周报生成时教师收到通知
- [ ] 通知列表页正常显示并分页
- [ ] 单条和全部标记已读功能正常
- [ ] 导航栏铃铛显示未读计数
- [ ] 无导入错误，app 正常启动

## 参考代码模式

- 模型定义参考 `app/models/conversation.py`
- 分页模式参考 SQLAlchemy `offset().limit()` + `count()`
- 相对时间显示：前端用简单 JS 函数（或引入 dayjs CDN）计算"x分钟前"
- 路由注册参考 `app/main.py` 中 `app.include_router(analytics_router)` 的模式
