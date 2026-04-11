# 巨量剪辑工具 — 用户系统接入文档

## 概述

巨量剪辑工具（本地 EXE 程序）需要接入视频混剪系统的用户认证体系，实现"登录后才能使用"的权限控制。

**核心流程：**

```
EXE 启动 → 显示登录界面 → 调用登录接口 → 获取 Token → 使用 Token 调用业务接口
```

**权限规则：**

- 管理员（`super_admin` / `admin`）：自动拥有 KK 剪辑使用权限
- 普通用户（`user`）：需要管理员在「用户管理」页面勾选「巨量剪辑工具 → 登录权限」后才能登录
- 未勾选任何权限的普通用户（默认全部权限）：也可以使用 KK 剪辑

---

## 接口说明

### 基础信息

| 项目 | 值 |
|------|-----|
| 基础 URL | `http://{服务器地址}:8080/api/v1` |
| 认证方式 | Bearer Token（JWT） |
| Token 有效期 | 7 天 |
| 请求格式 | `Content-Type: application/json` |

### 统一响应格式

**成功响应**（HTTP 200）：

```json
{
    "code": 0,
    "message": "ok",
    "data": { ... }
}
```

**错误响应**（HTTP 400 / 401 / 403）：

```json
{
    "detail": "错误描述（可直接展示给用户）"
}
```

---

### 1. 登录接口

用户输入邮箱和密码，调用此接口获取 Token。

**请求：**

```
POST /api/v1/auth/login
Content-Type: application/json
```

**请求体：**

```json
{
    "email": "user@example.com",
    "password": "123456",
    "client": "kk_clip"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| email | string | 是 | 用户邮箱 |
| password | string | 是 | 用户密码 |
| client | string | 是 | **必须传 `"kk_clip"`**，服务端据此校验 KK 剪辑权限 |

**成功响应**（HTTP 200）：

```json
{
    "code": 0,
    "message": "ok",
    "data": {
        "access_token": "eyJhbGciOiJIUzI1NiIs...",
        "token_type": "bearer",
        "user": {
            "id": 1,
            "email": "user@example.com",
            "nickname": "张三",
            "role": "user",
            "is_active": true,
            "permissions": ["/material", "kk-clip-login"],
            "created_at": "2025-01-01 12:00:00",
            "updated_at": "2025-01-01 12:00:00"
        }
    }
}
```

| 字段 | 说明 |
|------|------|
| `data.access_token` | JWT Token，后续请求需在 Header 中携带 |
| `data.token_type` | 固定为 `"bearer"` |
| `data.user` | 用户基本信息 |
| `data.user.role` | 角色：`super_admin` / `admin` / `user` |
| `data.user.permissions` | 权限列表，`null` 表示拥有全部权限 |

**错误响应示例：**

| HTTP 状态码 | detail | 场景 |
|------------|--------|------|
| 400 | `"邮箱或密码错误"` | 邮箱不存在或密码错误 |
| 400 | `"账号已被禁用，请联系管理员"` | 账号被管理员禁用 |
| 400 | `"您没有巨量剪辑工具的使用权限，请联系管理员开通"` | 用户没有 KK 剪辑权限 |

---

### 2. 获取当前用户信息

用于验证 Token 是否有效，以及获取最新的用户信息。建议在 EXE 启动时调用此接口验证本地缓存的 Token 是否仍然有效。

**请求：**

```
GET /api/v1/auth/me
Authorization: Bearer {access_token}
```

**成功响应**（HTTP 200）：

```json
{
    "code": 0,
    "message": "ok",
    "data": {
        "id": 1,
        "email": "user@example.com",
        "nickname": "张三",
        "role": "user",
        "is_active": true,
        "permissions": ["/material", "kk-clip-login"],
        "created_at": "2025-01-01 12:00:00",
        "updated_at": "2025-01-01 12:00:00"
    }
}
```

**错误响应：**

| HTTP 状态码 | detail | 场景 |
|------------|--------|------|
| 401 | `"无效或过期的令牌"` | Token 过期或被篡改 |
| 401 | `"用户不存在"` | 用户已被删除 |
| 403 | `"账号已被禁用"` | 账号被管理员禁用 |

---

## 接入指南

### 推荐的认证流程

```
┌─────────────────────────────────────────────────────┐
│                    EXE 启动                          │
│                       │                              │
│              检查本地是否有缓存 Token                  │
│                   ┌───┴───┐                          │
│                   │       │                          │
│                  有      无                           │
│                   │       │                          │
│         GET /auth/me     显示登录界面                  │
│         验证 Token       用户输入邮箱密码              │
│          ┌──┴──┐              │                      │
│         成功  失败     POST /auth/login               │
│          │     │       (client: "kk_clip")            │
│          │     │          ┌──┴──┐                     │
│   进入主界面  清除Token   成功  失败                    │
│                │          │     │                     │
│            显示登录界面   缓存Token  显示错误信息        │
│                          进入主界面                    │
└─────────────────────────────────────────────────────┘
```

### 代码示例（伪代码）

#### 登录

```python
import requests

API_BASE = "http://your-server:8080/api/v1"

def login(email: str, password: str) -> dict:
    resp = requests.post(f"{API_BASE}/auth/login", json={
        "email": email,
        "password": password,
        "client": "kk_clip"
    })

    if resp.status_code == 200:
        data = resp.json()
        if data["code"] == 0:
            token = data["data"]["access_token"]
            user = data["data"]["user"]
            # 缓存 token 到本地（文件/注册表/配置）
            save_token(token)
            return {"success": True, "token": token, "user": user}

    # 登录失败
    error = resp.json()
    error_msg = error.get("detail", "登录失败")
    return {"success": False, "error": error_msg}
```

#### 验证 Token

```python
def verify_token(token: str) -> dict | None:
    resp = requests.get(f"{API_BASE}/auth/me", headers={
        "Authorization": f"Bearer {token}"
    })

    if resp.status_code == 200:
        data = resp.json()
        if data["code"] == 0:
            return data["data"]  # 用户信息

    # Token 无效，需要重新登录
    return None
```

#### 启动时的认证检查

```python
def check_auth_on_startup():
    token = load_cached_token()

    if token:
        user = verify_token(token)
        if user:
            return token, user  # Token 有效，直接进入主界面

    # 需要登录
    return None, None
```

### Token 使用说明

1. **存储**：登录成功后将 `access_token` 保存到本地（建议加密存储，如 Windows DPAPI）
2. **携带**：所有需要认证的请求在 Header 中添加 `Authorization: Bearer {token}`
3. **刷新**：Token 有效期 7 天，过期后需要重新登录
4. **失效处理**：收到 HTTP 401 响应时，清除本地 Token 并引导用户重新登录

### 错误处理建议

| 场景 | 建议处理方式 |
|------|------------|
| 登录失败 | 直接将 `detail` 字段内容展示给用户 |
| Token 过期（401） | 清除缓存，弹出登录界面 |
| 账号被禁用（403） | 提示用户联系管理员 |
| 网络错误 | 提示网络连接失败，允许重试 |
| 无 KK 剪辑权限（400） | 提示用户联系管理员开通权限 |

---

## 管理员操作指南

### 为用户开通 KK 剪辑权限

1. 使用管理员账号登录 Web 管理后台
2. 进入「系统管理 → 用户管理」
3. 找到目标用户，点击「编辑」
4. 在「功能权限」树中勾选「巨量剪辑工具 → 登录权限」
5. 点击「确定」保存

> **注意：** 如果用户没有勾选任何权限（即拥有全部权限），则自动拥有 KK 剪辑使用权限，无需单独勾选。只有在需要**限制用户只能使用部分功能**时，才需要手动勾选具体权限。
