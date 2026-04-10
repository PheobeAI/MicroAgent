# 设计文档：项目部署结构 — Config 查找与目录初始化（步骤 0）

**日期：** 2026-04-10
**状态：** 已确认
**关联：** engineering-design.md §7、memory-design.md 开发路线图步骤 0

---

## 背景

当前 `load_config()` 只从 exe 同级目录查找 `config.yaml`，日志路径硬编码在 `ui/logger.py` 中且与新规范不一致（`LOCALAPPDATA/PheobeAI/...` → `~\.pheobe\MicroAgent\`）。需要建立统一的路径权威来源，支持 memory 模块后续所有路径（db、logs、skills）使用同一套规范。

---

## 目标目录结构

```
~\.pheobe\MicroAgent\          ← USER_DIR，唯一持久化根目录
├── config.yaml
├── models\
├── memory\
├── logs\
└── skills\

<exe所在目录>\                 ← 发布包，不写入用户数据
├── microagent-<variant>.exe
├── config.yaml                ← fallback 模板
└── README.txt
```

---

## 核心组件

### 新建 `core/paths.py`

项目中唯一知道 `USER_DIR` 位置的模块，其他所有模块通过它获取路径。

**常量：**
```python
USER_DIR = Path.home() / ".pheobe" / "MicroAgent"
_SUBDIRS  = ("models", "memory", "logs", "skills")
```

**公开接口：**

| 函数 | 说明 |
|---|---|
| `get_exe_dir() -> Path` | exe 所在目录（开发时为 `main.py` 所在目录） |
| `find_config() -> Path` | 三步查找，不存在时自动 bootstrap，返回 config 路径 |
| `bootstrap_user_dir(template: Path | None) -> Path` | 创建目录树，写入/复制 config 模板 |
| `resolve_relative(config_dir: Path, value: str) -> Path` | 相对于 config_dir 解析路径，绝对路径直通 |
| `log_dir() -> Path` | `USER_DIR/logs`，不存在则创建 |

**`find_config()` 查找顺序：**
1. `USER_DIR / "config.yaml"` — 存在则直接返回
2. `get_exe_dir() / "config.yaml"` — 存在则直接返回
3. 都不存在 → 调用 `bootstrap_user_dir(template=exe_dir/config.yaml)` → 返回新建路径

**`bootstrap_user_dir()` 行为：**
1. 创建 `USER_DIR/{models,memory,logs,skills}`（幂等，`exist_ok=True`）
2. 若 template 路径存在 → `shutil.copy(template, USER_DIR/config.yaml)`
3. 否则写入内置默认配置模板
4. 打印初始化提示到 console（使用 `ui.console`）

**内置默认配置模板：**
```yaml
# MicroAgent 配置文件
# 所有路径均相对于本文件所在目录

model:
  path: models\gemma-4-e2b-instruct.gguf
  n_gpu_layers: -1
  n_threads: 6
  n_ctx: 131072
  max_tokens: 2048

agent:
  mode: tool_calling
  verbose: false
  show_thinking: true

tools:
  web_search:
    enabled: true
    tavily_api_key: ""
  file_manager:
    enabled: true
    allow_destructive: false
    allowed_dirs: []
  system_info:
    enabled: true

runtime:
  language: zh
  log_level: info
```

---

### 修改 `core/config.py`

移除当前内联的 model path 解析逻辑（第 70–72 行），该逻辑迁移到 `main.py`，由 `resolve_relative()` 统一处理：

```python
# 移除：
model_path = Path(config.model.path)
if not model_path.is_absolute():
    config.model.path = str((config_path.parent / model_path).resolve())
```

`load_config(config_path)` 其余逻辑不变：接收一个已知存在的 Path，解析 YAML，构建 `AppConfig`。

---

### 修改 `main.py`

```python
from core.paths import find_config, resolve_relative

# 替换原来的硬编码 config_path
config_path = find_config()
config = load_config(config_path)

# 统一路径解析（后续 memory.db_path 等在各自步骤中按同样方式处理）
config.model.path = str(resolve_relative(config_path.parent, config.model.path))
```

删除原来的 `if not config_path.exists(): console.print(...)` 警告（bootstrap 已覆盖此场景）。

---

### 修改 `ui/logger.py`

删除 `_log_dir()` 函数，改为从 `core.paths` 导入：

```python
from core.paths import log_dir  # 替换原 _log_dir()
```

`setup()` 函数内将 `log_dir = _log_dir()` 改为 `log_dir = log_dir()`，其余日志逻辑不变。

---

## 错误处理

| 场景 | 处理方式 |
|---|---|
| 用户目录无写权限 | 捕获 `PermissionError`，打印明确错误并退出 |
| config.yaml 解析失败 | 现有 pydantic 校验已处理，保持不变 |
| bootstrap 时 template 复制失败 | 降级为写入内置默认模板，不中断启动 |

---

## 测试

**文件：** `tests/test_paths.py`

| 测试 | 方法 |
|---|---|
| `find_config` 优先返回用户目录 | mock `Path.home()`，预置 `USER_DIR/config.yaml` |
| `find_config` fallback 到 exe 同级 | mock home 无 config，预置 exe_dir config |
| `find_config` 触发 bootstrap | mock home 无 config，exe_dir 无 config |
| `bootstrap_user_dir` 创建子目录 | 用 `tmp_path`，验证四个子目录存在 |
| `bootstrap_user_dir` 复制 template | 提供 template path，验证 config 内容一致 |
| `bootstrap_user_dir` 写入默认 template | 不提供 template，验证 config.yaml 存在且可解析 |
| `resolve_relative` 绝对路径直通 | 输入绝对路径，输出不变 |
| `resolve_relative` 相对路径解析 | 输入 `models\foo.gguf`，验证与 config_dir 拼接正确 |

---

## 文件改动范围

| 文件 | 操作 |
|---|---|
| `core/paths.py` | 新建 |
| `tests/test_paths.py` | 新建 |
| `core/config.py` | 删除 model path 解析（3 行） |
| `main.py` | 替换 config_path 逻辑（约 5 行） |
| `ui/logger.py` | 替换 `_log_dir()` 为 import（约 6 行） |
