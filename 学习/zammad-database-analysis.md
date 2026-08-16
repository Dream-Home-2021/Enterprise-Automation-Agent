# Zammad 项目架构与数据库存储分析

> 分析时间：2026-06-19  
> 项目：Zammad Helpdesk v7.1.0  
> 部署方式：Docker Compose

---

## 一、Zammad 是什么项目？

Zammad 是一个**开源的帮助台/工单管理系统**（类似 Zendesk、ServiceNow），用 Ruby on Rails 开发。核心功能：

- **工单管理** — 客户提交问题 → 分配给客服 → 跟踪 → 关闭
- **多渠道接入** — 邮件、电话、聊天、社交媒体（Twitter/Facebook/Telegram/WhatsApp 等）
- **用户/组织管理** — 客户、客服、管理员，支持组织分组
- **角色与权限** — Admin / Agent / Customer 三级角色
- **自动化工单** — 触发器（Triggers）、定时任务（Schedulers）、宏（Macros）、SLA
- **知识库** — KB 文章管理
- **在线聊天** — 内置 Chat 功能
- **CTI 集成** — 电话系统集成
- **AI 功能** — AI Agent、AI 文本工具、AI 分析

---

## 二、存储架构：4 个存储组件

Zammad **不是用一个数据库**，而是 4 个存储组件各司其职：

```
┌─────────────────────────────────────────────────────────────────┐
│                         Zammad 存储架构                          │
├──────────────┬──────────────────────────────────────────────────┤
│              │                                                  │
│  PostgreSQL  │  主数据库 — 所有业务数据（128 张表）               │
│  (端口 5432) │  用户、工单、组、角色、设置、知识库、聊天记录...    │
│              │                                                  │
├──────────────┼──────────────────────────────────────────────────┤
│              │                                                  │
│  Redis       │  缓存 + 队列 + WebSocket 会话                    │
│  (端口 6379) │  后台任务队列、实时通知、session 存储             │
│              │                                                  │
├──────────────┼──────────────────────────────────────────────────┤
│              │                                                  │
│Elasticsearch │  全文搜索引擎                                     │
│  (端口 9200) │  工单搜索、用户搜索、全局搜索                      │
│              │  25 个索引（zammad_production_*）                 │
│              │                                                  │
├──────────────┼──────────────────────────────────────────────────┤
│              │                                                  │
│  Memcached   │  Rails 应用缓存                                   │
│ (端口 11211) │  页面缓存、片段缓存、设置缓存                     │
│              │                                                  │
└──────────────┴──────────────────────────────────────────────────┘
```

### 各组件分工详解

| 组件 | 角色 | 数据类型 | 持久化 |
|------|------|----------|--------|
| **PostgreSQL** | 主数据库 | 所有结构化业务数据 | ✅ Docker Volume: `postgresql-data` |
| **Elasticsearch** | 搜索引擎 | 全文索引（工单、用户、KB等） | ✅ Docker Volume: `elasticsearch-data` |
| **Redis** | 缓存+队列 | 后台任务队列、WebSocket、Session | ✅ Docker Volume: `redis-data` |
| **Memcached** | 应用缓存 | Rails 页面/片段/设置缓存 | ❌ 重启丢失 |
| **文件系统** | 附件存储 | 上传的文件、图片 | ✅ Docker Volume: `zammad-storage` |

---

## 三、PostgreSQL 数据库结构（核心）

数据库名：`zammad_production`，共 **128 张表**。按功能模块分类：

### 3.1 用户与权限模块

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `users` | 用户表 | `id`, `login`, `email`, `firstname`, `lastname`, `password`, `active`, `vip`, `organization_id`, `preferences` |
| `roles` | 角色表 | `id`, `name`（Admin/Agent/Customer）, `default_at_signup` |
| `roles_users` | 用户-角色关联 | `user_id`, `role_id` |
| `roles_groups` | 角色-组关联 | `role_id`, `group_id` |
| `permissions` | 权限定义 | `id`, `name` |
| `permissions_roles` | 权限-角色关联 | `permission_id`, `role_id` |
| `organizations` | 组织表 | `id`, `name`, `shared`, `domain`, `active`, `vip` |
| `organizations_users` | 组织-用户关联 | `organization_id`, `user_id` |
| `groups` | 组/队列表 | `id`, `name`, `signature_id`, `email_address_id`, `parent_id`, `assignment_timeout`, `follow_up_possible` |
| `groups_users` | 组-用户关联 | `group_id`, `user_id` |
| `tokens` | API Token | `id`, `user_id`, `name`, `token`, `persistent`, `action` |
| `authorizations` | OAuth 授权 | `id`, `user_id`, `provider`, `uid` |
| `user_devices` | 用户设备 | `user_id`, `ip`, `user_agent` |
| `user_two_factor_preferences` | 双因素认证 | `user_id`, `method` |

### 3.2 工单核心模块

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `tickets` | 工单表 | `id`, `title`, `number`, `group_id`, `priority_id`, `state_id`, `customer_id`, `owner_id`, `organization_id`, `article_count`, `time_unit`, `preferences`, `ai_agent_running` |
| `ticket_articles` | 工单回复/文章 | `id`, `ticket_id`, `type_id`, `sender_id`, `body`, `internal`, `subject`, `from`, `to`, `cc`, `content_type`, `origin_by_id` |
| `ticket_article_types` | 文章类型 | `id`, `name`（email/phone/note/web/chat/sms/twitter/telegram 等14种） |
| `ticket_article_senders` | 发件人类型 | `id`, `name`（Agent/Customer/System） |
| `ticket_article_flags` | 文章标记 | `ticket_article_id`, `key`, `value` |
| `ticket_states` | 工单状态 | `id`, `name`, `state_type_id`, `default_create`, `default_follow_up`, `default_close`, `ignore_escalation` |
| `ticket_state_types` | 状态类型 | `id`, `name`（new/open/pending reminder/pending action/closed/merged） |
| `ticket_priorities` | 工单优先级 | `id`, `name`（1 low / 2 normal / 3 high）, `default_create`, `ui_icon`, `ui_color` |
| `ticket_counters` | 工单计数器 | 内部计数用 |
| `ticket_daily_event_locks` | 每日事件锁 | 防止重复触发 |
| `ticket_time_accountings` | 工单计时 | `ticket_id`, `ticket_article_id`, `time_unit` |
| `ticket_time_accounting_types` | 计时类型 | `name` |
| `ticket_shared_draft_starts` | 共享草稿（开始） | `ticket_id`, `group_id` |
| `ticket_shared_draft_zooms` | 共享草稿（Zoom） | `ticket_id` |
| `checklists` | 检查清单 | `ticket_id` |
| `checklist_items` | 检查清单项 | `checklist_id`, `ticket_id`, `text`, `checked` |
| `checklist_templates` | 检查清单模板 | `name` |
| `checklist_template_items` | 检查清单模板项 | `checklist_template_id` |

### 3.3 自动化模块

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `triggers` | 触发器 | `name`, `condition`, `perform`, `active` |
| `macros` | 宏 | `name`, `perform`, `active`, `ux_flow_next_up` |
| `schedulers` | 定时任务 | `name`, `method`, `period`, `active` |
| `jobs` | 后台任务 | `name`, `method`, `arguments`, `active` |
| `delayed_jobs` | 延迟任务队列 | `handler`, `run_at`, `queue`, `attempts` |
| `slas` | SLA 服务级别协议 | `name`, `first_response_time`, `response_time`, `update_time`, `solution_time`, `calendar_id`, `condition` |
| `calendars` | 工作日历 | `name`, `timezone`, `business_hours`, `ical_url` |
| `core_workflows` | 核心工作流 | `name`, `object`, `condition`, `perform` |
| `postmaster_filters` | 邮件过滤器 | `name`, `match`, `perform` |

### 3.4 通知与活动模块

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `online_notifications` | 在线通知 | `user_id`, `object`, `o_id`, `type`, `seen` |
| `online_notification_standalones` | 独立通知 | `user_id`, `type` |
| `activity_streams` | 活动流 | `user_id`, `object`, `o_id`, `type`, `group_id` |
| `mentions` | 提及 | `user_id`, `mentionable_type`, `mentionable_id` |
| `recent_views` | 最近查看 | `user_id`, `object`, `o_id` |
| `recent_closes` | 最近关闭 | `user_id`, `ticket_id` |
| `taskbars` | 任务栏 | `user_id`, `key`, `callback`, `state` |

### 3.5 知识库模块

| 表名 | 说明 |
|------|------|
| `knowledge_bases` | 知识库 |
| `knowledge_base_translations` | 知识库翻译 |
| `knowledge_base_locales` | 知识库语言 |
| `knowledge_base_categories` | KB 分类 |
| `knowledge_base_category_translations` | 分类翻译 |
| `knowledge_base_answers` | KB 答案/文章 |
| `knowledge_base_answer_translations` | 答案翻译 |
| `knowledge_base_answer_translation_contents` | 答案内容 |
| `knowledge_base_menu_items` | KB 菜单项 |
| `knowledge_base_permissions` | KB 权限 |

### 3.6 聊天模块

| 表名 | 说明 |
|------|------|
| `chats` | 聊天频道 |
| `chat_sessions` | 聊天会话 |
| `chat_messages` | 聊天消息 |
| `chat_agents` | 聊天客服 |

### 3.7 存储与文件模块

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `stores` | 存储记录 | `store_object_id`, `store_file_id`, `o_id`, `filename`, `size`, `preferences` |
| `store_files` | 存储文件元数据 | `id`, `name`, `size`, `preferences`, `store_provider_db_id` |
| `store_objects` | 存储对象类型 | `id`, `name` |
| `store_provider_dbs` | 存储提供者 | `id`, `name` |
| `avatars` | 用户头像 | `user_id`, `store_id` |

> 实际文件数据存储在 Docker Volume `zammad-storage`（`/opt/zammad/storage`），数据库只存元数据。

### 3.8 系统配置模块

| 表名 | 说明 |
|------|------|
| `settings` | 系统设置（288+ 条记录） |
| `signatures` | 邮件签名 |
| `email_addresses` | 邮件地址 |
| `channels` | 渠道配置（邮件/社交媒体等） |
| `external_credentials` | 外部凭证（OAuth等） |
| `external_syncs` | 外部同步 |
| `webhooks` | Webhook 配置 |
| `pgp_keys` | PGP 加密密钥 |
| `smime_certificates` | S/MIME 证书 |
| `ssl_certificates` | SSL 证书 |
| `ldap_sources` | LDAP 数据源 |
| `locales` | 语言包 |
| `translations` | 翻译 |
| `packages` | 插件包 |
| `package_migrations` | 插件迁移 |
| `import_jobs` | 导入任务 |
| `report_profiles` | 报表配置 |
| `overviews` | 概览视图 |
| `overviews_groups` | 概览-组关联 |
| `overviews_roles` | 概览-角色关联 |
| `overviews_users` | 概览-用户关联 |
| `templates` | 模板 |
| `text_modules` | 文本模块（快捷回复） |
| `public_links` | 公开链接 |

### 3.9 AI 模块

| 表名 | 说明 |
|------|------|
| `ai_agents` | AI Agent 配置 |
| `ai_analytics_runs` | AI 分析运行记录 |
| `ai_analytics_usages` | AI 分析使用量 |
| `ai_stored_results` | AI 存储结果 |
| `ai_text_tools` | AI 文本工具 |
| `ai_text_tools_groups` | AI 文本工具-组关联 |

### 3.10 历史审计模块

| 表名 | 说明 |
|------|------|
| `histories` | 操作历史 |
| `history_types` | 历史类型 |
| `history_objects` | 历史对象 |
| `history_attributes` | 历史属性 |

### 3.11 CTI（电话）模块

| 表名 | 说明 |
|------|------|
| `cti_caller_ids` | 来电号码识别 |
| `cti_logs` | CTI 日志 |

---

## 四、当前数据快照

### 4.1 用户

| id | login | firstname | lastname | email | active |
|----|-------|-----------|----------|-------|--------|
| 1 | - | - | | (系统用户) | ❌ |
| 2 | nicole.braun@zammad.org | Nicole | Braun | nicole.braun@zammad.org | ✅ |
| 3 | fanglongsheng1106@gmail.com | a | b | fanglongsheng1106@gmail.com | ✅ |
| 36 | user1@qq.com | | | user1@qq.com | ✅ |

### 4.2 角色

| id | name | default_at_signup | 说明 |
|----|------|-------------------|------|
| 1 | Admin | ❌ | 系统管理员 |
| 2 | Agent | ❌ | 客服人员 |
| 3 | Customer | ✅ | 客户（默认注册角色） |

### 4.3 工单状态

| id | name | state_type_id | default_create | default_close |
|----|------|---------------|----------------|---------------|
| 1 | new | 1 (new) | ✅ | ❌ |
| 2 | open | 2 (open) | ❌ | ❌ |
| 3 | pending reminder | 3 (pending reminder) | ❌ | ❌ |
| 6 | pending close | 4 (pending action) | ❌ | ❌ |
| 4 | closed | 5 (closed) | ❌ | ✅ |
| 5 | merged | 6 (merged) | ❌ | ❌ |

### 4.4 工单优先级

| id | name | default_create |
|----|------|----------------|
| 1 | 1 low | ❌ |
| 2 | 2 normal | ✅ |
| 3 | 3 high | ❌ |

### 4.5 工单文章类型（14种）

| id | name | communication |
|----|------|---------------|
| 1 | email | ✅ |
| 2 | sms | ✅ |
| 3 | chat | ✅ |
| 4 | fax | ✅ |
| 5 | phone | ✅ |
| 6 | twitter status | ✅ |
| 7 | twitter direct-message | ✅ |
| 8 | facebook feed post | ✅ |
| 9 | facebook feed comment | ✅ |
| 10 | note | ❌ |
| 11 | web | ✅ |
| 12 | telegram personal-message | ✅ |
| 13 | facebook direct-message | ✅ |
| 14 | whatsapp message | ✅ |

### 4.6 发件人类型

| id | name |
|----|------|
| 1 | Agent |
| 2 | Customer |
| 3 | System |

### 4.7 组

| id | name | note |
|----|------|------|
| 1 | Users | Standard Group/Pool for Tickets. |

---

## 五、Agent 操作数据库指南

如果你要写 Agent 直接操作数据库（不通过 API），以下是关键注意事项：

### 5.1 连接信息

```
Host: localhost (或 Docker 网络内 zammad-postgresql)
Port: 5432
Database: zammad_production
User: zammad
Password: zammad
```

### 5.2 创建工单（最小字段）

```sql
-- 1. 创建工单
INSERT INTO tickets (
  group_id, priority_id, state_id, organization_id,
  number, title, owner_id, customer_id,
  article_count, ai_agent_running,
  updated_by_id, created_by_id,
  created_at, updated_at
) VALUES (
  1,                    -- group_id (Users)
  2,                    -- priority_id (2 normal)
  1,                    -- state_id (new)
  NULL,                 -- organization_id
  '53002',              -- number (需唯一，建议取当前最大+1)
  'Test ticket title',  -- title
  1,                    -- owner_id (系统用户)
  2,                    -- customer_id (实际客户用户ID)
  0,                    -- article_count
  false,                -- ai_agent_running
  1,                    -- updated_by_id
  1,                    -- created_by_id
  NOW(), NOW()
) RETURNING id;

-- 2. 创建工单文章（回复内容）
INSERT INTO ticket_articles (
  ticket_id, type_id, sender_id,
  body, internal, content_type,
  updated_by_id, created_by_id,
  created_at, updated_at
) VALUES (
  <上一步返回的id>,     -- ticket_id
  11,                   -- type_id (web)
  2,                    -- sender_id (Customer)
  'Ticket body text',   -- body
  false,                -- internal
  'text/html',          -- content_type
  1,                    -- updated_by_id
  1,                    -- created_by_id
  NOW(), NOW()
);

-- 3. 更新工单 article_count
UPDATE tickets SET article_count = 1 WHERE id = <ticket_id>;
```

### 5.3 创建用户（最小字段）

```sql
INSERT INTO users (
  login, firstname, lastname, email,
  password, active, vip, verified,
  department, street, zip, city, country, address, note, source,
  login_failed, out_of_office,
  updated_by_id, created_by_id,
  created_at, updated_at
) VALUES (
  'newuser@example.com',  -- login
  'John',                 -- firstname
  'Doe',                  -- lastname
  'newuser@example.com',  -- email
  '$argon2id$...',        -- password (需 Rails 加密)
  true,                   -- active
  false,                  -- vip
  false,                  -- verified
  '', '', '', '', '', '', '', '',
  0, false,
  1, 1,
  NOW(), NOW()
) RETURNING id;

-- 关联角色
INSERT INTO roles_users (user_id, role_id) VALUES (<user_id>, 3); -- 3=Customer
```

### 5.4 ⚠️ 重要注意事项

1. **密码加密** — Zammad 使用 Argon2id 加密，不能直接写明文。建议通过 API 创建用户让系统自动加密，或用 Rails 的 `Password::Hashing` 方法。

2. **工单编号** — `number` 字段必须唯一，格式如 `53001`。建议查询 `SELECT MAX(number::int) FROM tickets` 后递增。

3. **时间戳** — 所有表都有 `created_at` 和 `updated_at`，必须手动设置。

4. **外键约束** — 大量外键关联，插入顺序：organizations → users → groups → tickets → ticket_articles。

5. **Elasticsearch 同步** — 直接写数据库不会自动同步到 ES 索引。需要通过 API 操作，或手动触发 `SearchIndexBackend.index(...)`。

6. **Redis 缓存** — 直接写 DB 后 Redis 缓存可能过期，建议操作后清理相关缓存。

7. **历史记录** — Zammad 会自动记录 histories，但直接写 DB 不会触发。

### 5.5 推荐方案

**强烈建议通过 API 操作数据**，原因：
- ✅ 自动处理密码加密
- ✅ 自动同步 Elasticsearch
- ✅ 自动触发通知、触发器、SLA 计算
- ✅ 自动记录操作历史
- ✅ 自动更新缓存
- ✅ 避免外键约束问题

仅在以下情况直接操作数据库：
- 批量数据导入/迁移
- 紧急数据修复
- 读取统计数据（只读）

---

## 六、Docker Volume 数据映射

| Volume 名称 | 容器内路径 | 存储内容 |
|-------------|-----------|----------|
| `postgresql-data` | `/var/lib/postgresql/data` | 所有 PostgreSQL 数据 |
| `elasticsearch-data` | `/usr/share/elasticsearch/data` | ES 索引数据 |
| `redis-data` | `/data` | Redis 持久化数据 |
| `zammad-storage` | `/opt/zammad/storage` | 上传的附件、头像等文件 |
| `zammad-backup` | `/var/tmp/zammad` | 自动备份数据 |

---

## 七、数据库 ER 关系简图

```
┌──────────┐     ┌──────────────┐     ┌──────────┐
│  roles   │◄────┤ roles_users   ├────►│  users   │
└──────────┘     └──────────────┘     └────┬─────┘
                                           │
┌──────────┐     ┌──────────────────┐      │
│  groups  │◄────┤ groups_users     ├──────┤
└────┬─────┘     └──────────────────┘      │
     │                                      │
     │         ┌─────────────────┐          │
     └────────►│     tickets     │◄─────────┘
               │  (customer_id)  │
               │  (owner_id)     │
               └────────┬────────┘
                        │
               ┌────────▼────────┐
               │ ticket_articles │
               └─────────────────┘

┌───────────────┐     ┌────────────────────┐
│ organizations │◄────┤ organizations_users │
└───────────────┘     └────────────────────┘
        ▲
        │ (organization_id)
   ┌────┴─────┐
   │  users   │
   └──────────┘
```
