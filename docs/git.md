# Git 日常开发流程

## 当前项目配置

- **远程仓库**：`https://github.com/Dream-Home-2021/My-Agent.git`
- **主分支**：`main`（永远可运行）
- **开发分支**：`feature/*`（每个能力一个分支）

---

## 一、日常开发流程（3 步走）

### ① 写代码前：创建 feature 分支

```bash
git checkout -b feature/tools   # 从当前分支新建并切换
```

这样你在 `feature/tools` 里随便改，不会弄坏 `main`。

### ② 写代码中：阶段性 commit

```bash
git add -A                          # 把所有改动暂存
git commit -m "feat: add search tool"   # 提交
```

commit 就像游戏存档，随时可以回退。

### ③ 写完后：合并回 main 并推送

```bash
git checkout main                   # 切回 main
git merge feature/tools             # 把功能分支合并进来
git push                            # 推送到 GitHub
```

---

## 二、分支命名规范

| 分支类型 | 命名规则 | 示例 |
|---------|---------|------|
| 功能开发 | `feature/<能力名>` | `feature/tools`、`feature/memory`、`feature/graph` |
| 修复 Bug | `fix/<问题描述>` | `fix/login-error` |
| 热修复 | `hotfix/<问题描述>` | `hotfix/security-patch` |

---

## 三、Commit 消息规范

```
<type>: <简短描述>
```

| type | 含义 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat: add vector search tool` |
| `fix` | 修复 Bug | `fix: correct state reset logic` |
| `refactor` | 重构 | `refactor: split graph into nodes` |
| `chore` | 杂务（配置、文档等） | `chore: init project structure` |
| `docs` | 文档 | `docs: update API reference` |

---

## 四、救命命令（出事了用）

### 撤销改动

| 场景 | 命令 |
|------|------|
| 撤销某个文件的改动（未暂存） | `git checkout -- <file>` |
| 撤销暂存（已 add 未 commit） | `git reset HEAD <file>` |
| 撤销最近一次 commit（保留代码） | `git reset --soft HEAD~1` |
| 撤销最近一次 commit（丢弃代码） | `git reset --hard HEAD~1` |
| 回退到某个历史 commit | `git reset --hard <commit-id>` |

### 查看状态

| 场景 | 命令 |
|------|------|
| 查看当前状态 | `git status` |
| 查看改了什么（未暂存） | `git diff` |
| 查看改了什么（已暂存） | `git diff --cached` |
| 查看提交历史 | `git log --oneline` |
| 查看某个文件的改动历史 | `git log --oneline <file>` |

### 分支操作

| 场景 | 命令 |
|------|------|
| 查看所有分支 | `git branch -a` |
| 切换分支 | `git checkout <branch>` |
| 删除本地分支 | `git branch -d <branch>` |
| 删除远程分支 | `git push origin --delete <branch>` |

---

## 五、CLAUDE.md 规则对应

| 规则 | 做法 |
|------|------|
| main 永远可运行 | 只在 feature 分支开发，测试完再 merge |
| 每个能力 = 一个 feature 分支 | `feature/tools`、`feature/memory`、`feature/graph`... |
| LangGraph 按 node 拆分开发 | 每个 node 可以单独一个 feature 分支 |
| Tool Calling 独立封装 | 放在 `feature/tools` 分支 |
| 改动可回滚 | 每个小功能一个 commit，出问题 `git reset` 回去 |

---

## 六、完整示例：开发一个搜索工具

```bash
# 1. 创建功能分支
git checkout -b feature/tools

# 2. 写代码...（编辑 src/tools/search.py 等文件）

# 3. 阶段性提交
git add -A
git commit -m "feat: add search tool with keyword matching"

# 4. 继续写代码...
git add -A
git commit -m "feat: add semantic search with embeddings"

# 5. 开发完成，测试通过，合并回 main
git checkout main
git merge feature/tools

# 6. 推送到远程
git push

# 7. 删除已合并的功能分支（可选）
git branch -d feature/tools
git push origin --delete feature/tools
```

---

## 七、常见问题

### Q: 合并时出现冲突怎么办？

```bash
# 合并时 Git 会提示哪些文件有冲突
git merge feature/tools

# 打开冲突文件，找到 <<<<<<< ======= >>>>>>> 标记
# 手动选择保留哪部分代码，删除标记

# 解决后重新提交
git add -A
git commit -m "fix: resolve merge conflict"
```

### Q: 不小心在 main 上直接提交了怎么办？

```bash
# 把提交移到 feature 分支
git checkout -b feature/my-fix    # 新分支会带着你的提交
git checkout main
git reset --hard HEAD~1           # main 回退一步
```

### Q: 想看看某个 commit 改了什么？

```bash
git show <commit-id>
```
