# Zammad 部署状态与 API 文档总结

> 更新时间：2026-06-19  
> 项目路径：`D:\GameDownload\My-agent\zammad-docker-compose`  
> 访问地址：`http://localhost:8080`

---

## 一、部署状态

所有组件已正常运行：

| 组件 | 容器名 | 状态 |
|------|--------|------|
| Nginx（反向代理） | `zammad-docker-compose-zammad-nginx-1` | ✅ Up |
| Rails Server（应用核心） | `zammad-docker-compose-zammad-railsserver-1` | ✅ Up (healthy) |
| WebSocket | `zammad-docker-compose-zammad-websocket-1` | ✅ Up |
| Scheduler（后台任务调度） | `zammad-docker-compose-zammad-scheduler-1` | ✅ Up |
| Backup（备份容器） | `zammad-docker-compose-zammad-backup-1` | ✅ Up |
| PostgreSQL 17（数据库） | `zammad-docker-compose-zammad-postgresql-1` | ✅ Up (healthy) |
| Redis 8.8（缓存/队列） | `zammad-docker-compose-zammad-redis-1` | ✅ Up (healthy) |
| Memcached（Rails 缓存） | `zammad-docker-compose-zammad-memcached-1` | ✅ Up (healthy) |
| Elasticsearch 9.4.2（全文搜索） | `zammad-docker-compose-zammad-elasticsearch-1` | ✅ Up |

---

## 二、管理员账号

| 信息 | 值 |
|------|-----|
| 用户名 / 邮箱 | `fanglongsheng1106@gmail.com` |
| 密码 | `Zammad2026!` |
| 访问地址 | `http://localhost:8080` |

---

## 三、API 凭证

| 认证方式 | 凭证 |
|----------|------|
| **Token Auth**（推荐） | `eJKVJDLvTXz720d080o6PkqOB4Dc-grK2N2Xr6V0ozaCBSZiGPmip4PA2-FIHs0O` |
| **HTTP Basic Auth** | `fanglongsheng1106@gmail.com` / `Zammad2026!` |
| **基础 URL** | `http://localhost:8080/api/v1` |

API 调用示例：

```bash
# Token 方式（推荐）
curl -H "Authorization: Token token=eJKVJDLvTXz720d080o6PkqOB4Dc-grK2N2Xr6V0ozaCBSZiGPmip4PA2-FIHs0O" \
  http://localhost:8080/api/v1/users/me

# Basic Auth 方式
curl -u "fanglongsheng1106@gmail.com:Zammad2026!" \
  http://localhost:8080/api/v1/users/me
```

---

## 四、API 使用说明

### 4.1 认证方式（三选一）

| 方式 | Header |
|------|--------|
| Token Auth（推荐） | `Authorization: Token token={your_token}` |
| HTTP Basic Auth | `Authorization: Basic base64(user:pass)` |
| OAuth2 | `Authorization: Bearer {token}` |

### 4.2 通用参数

| 参数 | 说明 |
|------|------|
| `?expand=true` | 将关联 ID 解析为完整对象 |
| `?page=1&per_page=5` | 分页（硬限制，不可配置更大值） |
| `?with_total_count=true` | 响应中包含总记录数 |
| `?only_total_count=true` | 仅返回总记录数 |
| `?full=true` | 返回完整资产 + 总数 |
| `Content-Type: application/json` | 请求体格式 |

### 4.3 搜索 API

```
# 工单搜索
GET /api/v1/tickets/search?query=welcome

# 用户搜索
GET /api/v1/users/search?query=john

# 全局搜索（跨用户、工单、组织、知识库、聊天）
GET /api/v1/search?query=welcome
```

---

## 五、核心 API 资源

### 5.1 Tickets（工单）

| 操作 | 方法 | 端点 | 权限 |
|------|------|------|------|
| 列出 | GET | `/api/v1/tickets` | `ticket.agent` / `ticket.customer` |
| 查看 | GET | `/api/v1/tickets/{id}` | `ticket.agent` / `ticket.customer` |
| 创建 | POST | `/api/v1/tickets` | `ticket.agent` / `ticket.customer` |
| 更新 | PUT | `/api/v1/tickets/{id}` | `ticket.agent` / `ticket.customer` |
| 删除 | DELETE | `/api/v1/tickets/{id}` | `admin`（永久删除） |

**创建工单示例：**
```json
POST /api/v1/tickets
{
  "title": "Login issue",
  "group": "Users",
  "customer": "john@example.com",
  "article": {
    "subject": "Help",
    "body": "I cannot log in.",
    "type": "web",
    "internal": false
  }
}
```

**更新工单示例：**
```json
PUT /api/v1/tickets/1
{
  "title": "Updated title",
  "state": "closed",
  "article": {
    "body": "Issue resolved.",
    "type": "note",
    "internal": false
  }
}
```

### 5.2 Ticket Articles（工单回复/文章）

| 操作 | 方法 | 端点 | 权限 |
|------|------|------|------|
| 列出（按工单） | GET | `/api/v1/ticket_articles/by_ticket/{ticket_id}` | `ticket.agent` / `ticket.customer` |
| 查看 | GET | `/api/v1/ticket_articles/{article_id}` | `ticket.agent` / `ticket.customer` |
| 创建 | POST | `/api/v1/ticket_articles` | `ticket.agent` / `ticket.customer` |
| 附件下载 | GET | `/api/v1/ticket_attachment/{t_id}/{a_id}/{att_id}` | `ticket.agent` / `ticket.customer` |

**创建回复示例：**
```json
POST /api/v1/ticket_articles
{
  "ticket_id": 1,
  "subject": "Re: Help",
  "body": "We are looking into this.",
  "content_type": "text/html",
  "type": "email",
  "internal": false,
  "sender": "Agent",
  "time_unit": "15"
}
```

**带附件的回复：**
```json
POST /api/v1/ticket_articles
{
  "ticket_id": 1,
  "body": "Please see attached...",
  "type": "note",
  "internal": false,
  "attachments": [
    {
      "filename": "report.txt",
      "data": "VGhlIGNha2UgaXMgYSBsaWUhCg==",
      "mime-type": "text/plain"
    }
  ]
}
```

### 5.3 Users（用户）

| 操作 | 方法 | 端点 | 权限 |
|------|------|------|------|
| 当前用户 | GET | `/api/v1/users/me` | 任意认证用户 |
| 列出 | GET | `/api/v1/users` | `ticket.agent` / `admin.user` |
| 查看 | GET | `/api/v1/users/{id}` | `ticket.agent` / `admin.user` |
| 创建 | POST | `/api/v1/users` | `admin.user` |
| 更新 | PUT | `/api/v1/users/{id}` | `admin.user` |
| 删除 | DELETE | `/api/v1/users/{id}` | `admin.user`（建议用隐私任务代替） |
| 隐私删除 | POST | `/api/v1/data_privacy_tasks` | `admin.data_privacy` |
| 隐私任务状态 | GET | `/api/v1/data_privacy_tasks/{id}` | `admin.data_privacy` |

**创建用户示例：**
```json
POST /api/v1/users
{
  "firstname": "Jane",
  "lastname": "Doe",
  "email": "jdoe@example.com",
  "login": "jdoe",
  "organization": "Example Corp",
  "roles": ["Agent", "Customer"]
}
```

### 5.4 Groups（组）

| 操作 | 方法 | 端点 | 权限 |
|------|------|------|------|
| 列出 | GET | `/api/v1/groups` | `admin.group` |
| 查看 | GET | `/api/v1/groups/{id}` | `admin.group` |
| 创建 | POST | `/api/v1/groups` | `admin.group` |
| 更新 | PUT | `/api/v1/groups/{id}` | `admin.group` |
| 删除 | DELETE | `/api/v1/groups/{id}` | `admin.group`（永久删除） |

**创建组示例：**
```json
POST /api/v1/groups
{
  "name": "Support Team",
  "signature_id": 1,
  "email_address_id": 3,
  "assignment_timeout": 180,
  "follow_up_possible": "new_ticket",
  "follow_up_assignment": false,
  "active": true,
  "note": "First level support"
}
```

> 子组用 `::` 分隔，如 `Sales::Europe::South`

### 5.5 Organizations（组织）

| 操作 | 方法 | 端点 | 权限 |
|------|------|------|------|
| 列出 | GET | `/api/v1/organizations` | `ticket.agent` / `admin.organization` |
| 查看 | GET | `/api/v1/organizations/{id}` | `ticket.agent` / `admin.organization` |
| 创建 | POST | `/api/v1/organizations` | `admin.organization` |
| 更新 | PUT | `/api/v1/organizations/{id}` | `admin.organization` |
| 删除 | DELETE | `/api/v1/organizations/{id}` | `admin.organization`（永久删除） |

**创建组织示例：**
```json
POST /api/v1/organizations
{
  "name": "Example Corp",
  "shared": true,
  "domain": "example.com",
  "domain_assignment": true,
  "active": true,
  "vip": false,
  "note": "Important customer",
  "members": ["user1@example.com", "user2@example.com"]
}
```

### 5.6 Roles（角色）

| 操作 | 方法 | 端点 | 权限 |
|------|------|------|------|
| 列出 | GET | `/api/v1/roles` | `admin.role` |
| 查看 | GET | `/api/v1/roles/{id}` | `admin.role` |
| 创建 | POST | `/api/v1/roles` | `admin.role` |
| 更新 | PUT | `/api/v1/roles/{id}` | `admin.role` |

**创建角色示例：**
```json
POST /api/v1/roles
{
  "name": "VIP service",
  "active": true,
  "default_at_signup": false,
  "group_ids": {"1": "full", "2": "full"},
  "permission_ids": ["57", "58"],
  "note": "Handling of VIP customers!"
}
```

### 5.7 Ticket States（工单状态）

| 操作 | 方法 | 端点 | 权限 |
|------|------|------|------|
| 列出 | GET | `/api/v1/ticket_states` | `admin.object` / `ticket.agent` / `ticket.customer` |
| 查看 | GET | `/api/v1/ticket_states/{id}` | `admin.object` / `ticket.agent` / `ticket.customer` |
| 创建 | POST | `/api/v1/ticket_states` | `admin.object` |
| 更新 | PUT | `/api/v1/ticket_states/{id}` | `admin.object` |
| 删除 | DELETE | `/api/v1/ticket_states/{id}` | `admin.object`（永久删除） |

### 5.8 Ticket Priorities（工单优先级）

| 操作 | 方法 | 端点 | 权限 |
|------|------|------|------|
| 列出 | GET | `/api/v1/ticket_priorities` | `admin.object` / `ticket.agent` / `ticket.customer` |
| 查看 | GET | `/api/v1/ticket_priorities/{id}` | `admin.object` / `ticket.agent` / `ticket.customer` |
| 创建 | POST | `/api/v1/ticket_priorities` | `admin.object` |
| 更新 | PUT | `/api/v1/ticket_priorities/{id}` | `admin.object` |
| 删除 | DELETE | `/api/v1/ticket_priorities/{id}` | `admin.object`（永久删除） |

### 5.9 Tags（标签）

**工单标签操作：**

| 操作 | 方法 | 端点 | 权限 |
|------|------|------|------|
| 列出工单标签 | GET | `/api/v1/tags?object=Ticket&o_id={id}` | `ticket.agent` / `admin.tag` |
| 添加标签 | POST | `/api/v1/tags/add` | `ticket.agent` / `admin.tag` |
| 移除标签 | DELETE | `/api/v1/tags/remove` | `ticket.agent` / `admin.tag` |

**标签管理：**

| 操作 | 方法 | 端点 | 权限 |
|------|------|------|------|
| 列出所有标签 | GET | `/api/v1/tag_list` | `admin.tag` |
| 创建标签 | POST | `/api/v1/tag_list` | `admin.tag` |
| 重命名标签 | PUT | `/api/v1/tag_list/{id}` | `admin.tag` |
| 删除标签 | DELETE | `/api/v1/tag_list/{id}` | `admin.tag` |

**添加标签示例：**
```json
POST /api/v1/tags/add
{
  "item": "urgent",
  "object": "Ticket",
  "o_id": 1
}
```

### 5.10 Mentions（提及）

| 操作 | 方法 | 端点 | 权限 |
|------|------|------|------|
| 列出 | GET | `/api/v1/mentions` | `ticket.agent` / `ticket.customer` |
| 创建 | POST | `/api/v1/mentions` | `ticket.agent` |
| 删除 | DELETE | `/api/v1/mentions/{id}` | `ticket.agent` |

### 5.11 Calendar（日历）

| 操作 | 方法 | 端点 | 权限 |
|------|------|------|------|
| 列出 | GET | `/api/v1/calendars` | `admin.calendar` |
| 查看 | GET | `/api/v1/calendars/{id}` | `admin.calendar` |
| 创建 | POST | `/api/v1/calendars` | `admin.calendar` |
| 更新 | PUT | `/api/v1/calendars/{id}` | `admin.calendar` |
| 删除 | DELETE | `/api/v1/calendars/{id}` | `admin.calendar`（永久删除） |

### 5.12 SLA（服务级别协议）

| 操作 | 方法 | 端点 | 权限 |
|------|------|------|------|
| 列出 | GET | `/api/v1/slas` | `admin.sla` |
| 查看 | GET | `/api/v1/slas/{id}` | `admin.sla` |
| 创建 | POST | `/api/v1/slas` | `admin.sla` |
| 更新 | PUT | `/api/v1/slas/{id}` | `admin.sla` |
| 删除 | DELETE | `/api/v1/slas/{id}` | `admin.sla`（永久删除） |

**创建 SLA 示例：**
```json
POST /api/v1/slas
{
  "name": "Standard SLA",
  "first_response_time": "120",
  "response_time": "",
  "update_time": "120",
  "solution_time": "120",
  "condition": {
    "ticket.state_id": {
      "operator": "is",
      "value": "2"
    }
  },
  "calendar_id": "1"
}
```

### 5.13 Object Manager Attributes（自定义对象属性）

| 操作 | 方法 | 端点 | 权限 |
|------|------|------|------|
| 列出 | GET | `/api/v1/object_manager_attributes` | `admin.object` |
| 查看 | GET | `/api/v1/object_manager_attributes/{id}` | `admin.object` |
| 创建 | POST | `/api/v1/object_manager_attributes` | `admin.object` |
| 更新 | PUT | `/api/v1/object_manager_attributes/{id}` | `admin.object` |
| 删除 | DELETE | `/api/v1/object_manager_attributes/{id}` | `admin.object` |
| 执行数据库迁移 | POST | `/api/v1/object_manager_attributes_execute_migrations` | `admin.object` |

支持的数据类型：`boolean`、`date`、`datetime`、`integer`、`select`、`input`、`tree_select`。

---

## 六、待配置项

| 项目 | 状态 | 说明 |
|------|------|------|
| HTTPS | ⚠️ 未配置 | 当前 HTTP，生产环境需配置 Nginx Proxy Manager + Let's Encrypt 或 Cloudflare Tunnel |
| 邮件渠道 | ⚠️ 未配置 | 未设置邮件接收/发送 |
| 备份调度 | ✅ 已内置 | 每天 03:00 备份，保留 10 天，数据存储在 Docker volume |
| 时区 | ⚠️ 需修改 | 默认 `Europe/Berlin`，建议改为 `Asia/Shanghai` |

---

## 七、Docker Compose 关键配置

- **Compose 文件**：`D:\GameDownload\My-agent\zammad-docker-compose\docker-compose.yml`
- **Zammad 版本**：`7.1.0`
- **数据库**：PostgreSQL 17，数据库名 `zammad_production`
- **端口映射**：`8080:8080`
- **数据卷**：`postgresql-data`、`elasticsearch-data`、`redis-data`、`zammad-backup`、`zammad-storage`

---

## 八、常用管理命令

```powershell
# 查看所有容器状态
docker ps --format "table {{.Names}}\t{{.Status}}"

# Rails 控制台
docker exec zammad-docker-compose-zammad-railsserver-1 bin/rails c

# Rails 执行单行命令
docker exec zammad-docker-compose-zammad-railsserver-1 bin/rails runner "puts User.count"

# 重置用户密码
docker exec zammad-docker-compose-zammad-railsserver-1 bin/rails runner "u = User.find(3); u.password = 'newpass'; u.save!"
```
