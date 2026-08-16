# pytest 断点调试配置

## 问题背景

在 VS Code 中用 pytest 调试测试用例时，断点打下去后调试器不停在断点位置，而是跑进 `BaseAgent.invoke` 或第三方库代码里。

原因：
1. 调试器启动时会执行所有 import 语句
2. import 触发第三方库初始化，调试器会追踪进去
3. `MagicMock` 是动态对象，属性访问会触发内部逻辑，调试器会追踪进去

## launch.json 配置

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "pytest: debug current test file",
            "type": "debugpy",
            "request": "launch",
            "module": "pytest",
            "args": ["${file}", "-v", "-s", "--tb=line"],
            "console": "integratedTerminal",
            "justMyCode": true,
            "env": {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1"
            }
        },
        {
            "name": "pytest: debug all tests",
            "type": "debugpy",
            "request": "launch",
            "module": "pytest",
            "args": ["tests/", "-v", "-s", "--tb=line"],
            "console": "integratedTerminal",
            "justMyCode": true
        },
        {
            "name": "pytest: debug with --pdb (auto-break on failure)",
            "type": "debugpy",
            "request": "launch",
            "module": "pytest",
            "args": ["${file}", "-v", "-s", "--pdb", "--tb=line"],
            "console": "integratedTerminal",
            "justMyCode": true
        }
    ]
}
```

## 配置项说明

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `type` | `debugpy` | Python 调试器 |
| `request` | `launch` | 启动新进程并附加调试器 |
| `module` | `pytest` | 用 pytest 运行器 |
| `args` | `["${file}", "-v", "-s", "--tb=line"]` | `-v` verbose、`-s` 不捕获 print、`--tb=line` 简化的 traceback |
| `console` | `integratedTerminal` | 在 VS Code 终端运行 |
| `justMyCode` | `true` | 只调试项目代码，跳过 site-packages |
| `PYTHONDONTWRITEBYTECODE` | `1` | 不生成 .pyc，避免缓存干扰 |
| `PYTHONUNBUFFERED` | `1` | 不缓冲 stdout，print 即时输出 |

## 三个配置的区别

| 配置名 | 何时用 |
|--------|--------|
| `pytest: debug current test file` | 只跑当前打开的测试文件，配合断点用 |
| `pytest: debug all tests` | 跑全部测试 |
| `pytest: debug with --pdb` | 不用手动打断点，失败时自动进调试器 |

## 使用方法

1. 打开测试文件（如 `tests/test_agent_node.py`）
2. 在代码行号前点红点打断点
3. 按 F5，选择 **"pytest: debug current test file"**
4. 调试器会在断点处停下

## 调试快捷键

| 快捷键 | 作用 |
|--------|------|
| F5 | 继续到下一个断点 |
| F10 | 单步跳过（不进入函数） |
| F11 | 单步进入（跳进函数内部） |
| Shift+F11 | 跳出当前函数 |
| 鼠标悬停变量 | 看当前值 |
| 底部"变量"面板 | 看所有局部变量 |
| 调试控制台 | 输入变量名查看值 |

## 注意事项

- 断点要打在**函数内部**，不要打在 `def` 那一行（def 行是函数定义，不是执行行）
- 如果断点显示灰色空心圆，说明代码没被运行到，检查路径是否正确
- `justMyCode: true` 会跳过所有第三方库代码，如果调试时进了第三方代码，检查这个配置
- 如果调试器还是乱跑，尝试用 F10（Step Over）代替 F11（Step Into）

## conftest.py 配合

在 `tests/conftest.py` 中放路径配置，避免测试文件顶部写 import 代码导致调试器追踪：

```python
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
```

这样测试文件本身干干净净，调试器不会在 import 阶段就跑偏。
