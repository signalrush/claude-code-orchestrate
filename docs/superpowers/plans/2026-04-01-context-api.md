# Context API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `ctx` module backed by OpenViking that provides persistent, project-scoped context management (put/get/ls/search/rm) for orchestration scripts.

**Architecture:** Singleton AGFSClient lazily connects to OpenViking server (auto-starts if not running). All context is stored under `/orchestrate/{project}/` in the virtual filesystem. 6 module-level functions match the existing SDK pattern.

**Tech Stack:** Python 3.10+, openviking (AGFSClient), existing ClaudeCodeError

---

### Task 1: Context Module — Server Connection & Init

**Files:**
- Create: `claude_code_orchestrate/context.py`
- Create: `tests/test_context.py`

- [ ] **Step 1: Write failing test for init and server connection**

```python
# tests/test_context.py
from unittest.mock import patch, MagicMock
import claude_code_orchestrate.context as ctx_mod


def setup_function():
    """Reset singletons before each test."""
    ctx_mod._client = None
    ctx_mod._server_proc = None
    ctx_mod._project = None


def _mock_agfs():
    client = MagicMock()
    client.health = MagicMock(return_value={"status": "ok"})
    client.mkdir = MagicMock(return_value={})
    return client


def test_init_sets_project_and_creates_dir():
    client = _mock_agfs()
    with patch("claude_code_orchestrate.context.AGFSClient", return_value=client):
        ctx_mod.init("my-project")
        assert ctx_mod._project == "my-project"
        client.mkdir.assert_any_call("/orchestrate")
        client.mkdir.assert_any_call("/orchestrate/my-project")


def test_prefix_raises_without_init():
    from claude_code_orchestrate.mcp_transport import ClaudeCodeError
    try:
        ctx_mod._prefix()
        assert False, "Should have raised"
    except ClaudeCodeError as e:
        assert "init" in str(e).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_code_orchestrate.context'`

- [ ] **Step 3: Implement context.py with server connection and init**

```python
# claude_code_orchestrate/context.py
import atexit
import subprocess
import time

from openviking import AGFSClient
from claude_code_orchestrate.mcp_transport import ClaudeCodeError

_client: AGFSClient | None = None
_server_proc: subprocess.Popen | None = None
_project: str | None = None


def _stop_server() -> None:
    global _server_proc
    if _server_proc:
        try:
            _server_proc.terminate()
            _server_proc.wait(timeout=5)
        except Exception:
            _server_proc.kill()
        _server_proc = None


def _ensure_server() -> AGFSClient:
    global _client, _server_proc
    if _client is not None:
        return _client

    # Try connecting to existing server
    client = AGFSClient("http://localhost:1933")
    try:
        client.health()
        _client = client
        return _client
    except Exception:
        pass

    # Server not running — spawn it
    _server_proc = subprocess.Popen(
        ["openviking-server"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    atexit.register(_stop_server)

    # Wait for health check (up to 5s)
    for _ in range(50):
        try:
            client.health()
            _client = client
            return _client
        except Exception:
            time.sleep(0.1)

    raise ClaudeCodeError("ctx", "Failed to start openviking-server")


def _prefix() -> str:
    if _project is None:
        raise ClaudeCodeError("ctx", "Call ctx.init(project_name) first")
    return f"/orchestrate/{_project}"


def init(project: str) -> None:
    """Set the active project scope. Required before any other ctx call."""
    global _project
    _project = project
    client = _ensure_server()
    try:
        client.mkdir("/orchestrate")
    except Exception:
        pass
    try:
        client.mkdir(f"/orchestrate/{project}")
    except Exception:
        pass
```

- [ ] **Step 4: Run tests**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_context.py -v`
Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add claude_code_orchestrate/context.py tests/test_context.py
git commit -m "feat: context module with server auto-start and init"
```

---

### Task 2: put and get Functions

**Files:**
- Modify: `claude_code_orchestrate/context.py`
- Modify: `tests/test_context.py`

- [ ] **Step 1: Write failing tests for put and get**

```python
# append to tests/test_context.py

def test_put_writes_to_correct_path():
    client = _mock_agfs()
    with patch("claude_code_orchestrate.context.AGFSClient", return_value=client):
        ctx_mod.init("test-proj")
        ctx_mod.put("analysis", "some findings")
        client.write.assert_called_once_with("/orchestrate/test-proj/analysis", b"some findings")


def test_put_creates_parent_dirs():
    client = _mock_agfs()
    with patch("claude_code_orchestrate.context.AGFSClient", return_value=client):
        ctx_mod.init("test-proj")
        ctx_mod.put("phase-1/findings", "data")
        client.mkdir.assert_any_call("/orchestrate/test-proj/phase-1")


def test_get_reads_from_correct_path():
    client = _mock_agfs()
    client.cat = MagicMock(return_value=b"stored content")
    with patch("claude_code_orchestrate.context.AGFSClient", return_value=client):
        ctx_mod.init("test-proj")
        result = ctx_mod.get("analysis")
        client.cat.assert_called_once_with("/orchestrate/test-proj/analysis")
        assert result == "stored content"


def test_put_get_roundtrip():
    client = _mock_agfs()
    stored = {}

    def fake_write(path, data):
        stored[path] = data
        return path

    def fake_cat(path):
        return stored[path]

    client.write = MagicMock(side_effect=fake_write)
    client.cat = MagicMock(side_effect=fake_cat)

    with patch("claude_code_orchestrate.context.AGFSClient", return_value=client):
        ctx_mod.init("test-proj")
        ctx_mod.put("key", "hello world")
        result = ctx_mod.get("key")
        assert result == "hello world"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_context.py::test_put_writes_to_correct_path -v`
Expected: FAIL — `AttributeError: module has no attribute 'put'`

- [ ] **Step 3: Implement put and get**

Append to `claude_code_orchestrate/context.py`:

```python
def put(key: str, value: str) -> None:
    """Store context at key, relative to project scope."""
    client = _ensure_server()
    path = f"{_prefix()}/{key}"
    # Ensure parent directory exists
    parent = "/".join(path.split("/")[:-1])
    if parent:
        try:
            client.mkdir(parent)
        except Exception:
            pass
    client.write(path, value.encode())


def get(key: str) -> str:
    """Retrieve context by key."""
    client = _ensure_server()
    path = f"{_prefix()}/{key}"
    data = client.cat(path)
    if isinstance(data, bytes):
        return data.decode()
    return str(data)
```

- [ ] **Step 4: Run tests**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_context.py -v`
Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add claude_code_orchestrate/context.py tests/test_context.py
git commit -m "feat: ctx.put and ctx.get for context storage and retrieval"
```

---

### Task 3: ls, search, rm Functions

**Files:**
- Modify: `claude_code_orchestrate/context.py`
- Modify: `tests/test_context.py`

- [ ] **Step 1: Write failing tests for ls, search, rm**

```python
# append to tests/test_context.py

def test_ls_returns_names():
    client = _mock_agfs()
    client.ls = MagicMock(return_value=[
        {"name": "analysis"},
        {"name": "phase-1"},
    ])
    with patch("claude_code_orchestrate.context.AGFSClient", return_value=client):
        ctx_mod.init("test-proj")
        result = ctx_mod.ls()
        client.ls.assert_called_once_with("/orchestrate/test-proj")
        assert result == ["analysis", "phase-1"]


def test_ls_with_prefix():
    client = _mock_agfs()
    client.ls = MagicMock(return_value=[{"name": "findings"}])
    with patch("claude_code_orchestrate.context.AGFSClient", return_value=client):
        ctx_mod.init("test-proj")
        result = ctx_mod.ls("phase-1/")
        client.ls.assert_called_once_with("/orchestrate/test-proj/phase-1")
        assert result == ["findings"]


def test_search_greps_project():
    client = _mock_agfs()
    client.grep = MagicMock(return_value=b"line1: match\nline2: match")
    with patch("claude_code_orchestrate.context.AGFSClient", return_value=client):
        ctx_mod.init("test-proj")
        result = ctx_mod.search("match")
        client.grep.assert_called_once_with("/orchestrate/test-proj", "match", recursive=True)
        assert "match" in result


def test_rm_removes_key():
    client = _mock_agfs()
    client.rm = MagicMock(return_value={})
    with patch("claude_code_orchestrate.context.AGFSClient", return_value=client):
        ctx_mod.init("test-proj")
        ctx_mod.rm("analysis")
        client.rm.assert_called_once_with("/orchestrate/test-proj/analysis", recursive=False)


def test_rm_recursive():
    client = _mock_agfs()
    client.rm = MagicMock(return_value={})
    with patch("claude_code_orchestrate.context.AGFSClient", return_value=client):
        ctx_mod.init("test-proj")
        ctx_mod.rm("phase-1/", recursive=True)
        client.rm.assert_called_once_with("/orchestrate/test-proj/phase-1/", recursive=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_context.py::test_ls_returns_names -v`
Expected: FAIL — `AttributeError: module has no attribute 'ls'`

- [ ] **Step 3: Implement ls, search, rm**

Append to `claude_code_orchestrate/context.py`:

```python
def ls(prefix: str = "") -> list[str]:
    """List stored context keys under the given prefix."""
    client = _ensure_server()
    path = f"{_prefix()}/{prefix}".rstrip("/")
    entries = client.ls(path)
    return [e["name"] for e in entries]


def search(query: str) -> str:
    """Search across all stored context in the project."""
    client = _ensure_server()
    results = client.grep(_prefix(), query, recursive=True)
    if isinstance(results, bytes):
        return results.decode()
    return str(results)


def rm(key: str, recursive: bool = False) -> None:
    """Remove context by key."""
    client = _ensure_server()
    path = f"{_prefix()}/{key}"
    client.rm(path, recursive=recursive)
```

- [ ] **Step 4: Run tests**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_context.py -v`
Expected: 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add claude_code_orchestrate/context.py tests/test_context.py
git commit -m "feat: ctx.ls, ctx.search, ctx.rm for context management"
```

---

### Task 4: Public API — Export ctx from \_\_init\_\_.py

**Files:**
- Modify: `claude_code_orchestrate/__init__.py`
- Create: `tests/test_ctx_import.py`

- [ ] **Step 1: Write failing test for ctx import**

```python
# tests/test_ctx_import.py
def test_ctx_importable():
    from claude_code_orchestrate import ctx
    assert hasattr(ctx, "init")
    assert hasattr(ctx, "put")
    assert hasattr(ctx, "get")
    assert hasattr(ctx, "ls")
    assert hasattr(ctx, "search")
    assert hasattr(ctx, "rm")
    assert callable(ctx.init)


def test_ctx_in_all():
    import claude_code_orchestrate
    assert "ctx" in claude_code_orchestrate.__all__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_ctx_import.py -v`
Expected: FAIL — `ImportError: cannot import name 'ctx'`

- [ ] **Step 3: Update __init__.py**

Replace the contents of `claude_code_orchestrate/__init__.py` with:

```python
from claude_code_orchestrate.client import (
    Read, Write, Edit, Glob, Grep,
    Bash,
    Agent, SendMessage, TaskOutput, TaskStop,
    WebFetch, WebSearch,
    CronCreate, CronDelete, CronList,
    TeamCreate, TeamDelete,
    RemoteTrigger,
    EnterWorktree, ExitWorktree,
    Skill, ToolSearch, NotebookEdit,
)
from claude_code_orchestrate.mcp_transport import ClaudeCodeError
from claude_code_orchestrate import context as ctx

__all__ = [
    "Read", "Write", "Edit", "Glob", "Grep",
    "Bash",
    "Agent", "SendMessage", "TaskOutput", "TaskStop",
    "WebFetch", "WebSearch",
    "CronCreate", "CronDelete", "CronList",
    "TeamCreate", "TeamDelete",
    "RemoteTrigger",
    "EnterWorktree", "ExitWorktree",
    "Skill", "ToolSearch", "NotebookEdit",
    "ClaudeCodeError",
    "ctx",
]
```

- [ ] **Step 4: Update test_init.py count**

In `tests/test_init.py`, change the `__all__` length assertion:

```python
def test_all_exports_listed():
    import claude_code_orchestrate
    assert len(claude_code_orchestrate.__all__) == 25
```

- [ ] **Step 5: Run all tests**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_ctx_import.py tests/test_init.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add claude_code_orchestrate/__init__.py tests/test_ctx_import.py tests/test_init.py
git commit -m "feat: export ctx module from package"
```

---

### Task 5: Integration Test with Live OpenViking Server

**Files:**
- Create: `tests/test_context_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_context_integration.py
"""
Integration tests that connect to a real OpenViking server.
Run with: pytest tests/test_context_integration.py -v -m integration
"""
import pytest

pytestmark = pytest.mark.integration


def setup_function():
    """Reset context module state before each test."""
    import claude_code_orchestrate.context as ctx_mod
    ctx_mod._client = None
    ctx_mod._server_proc = None
    ctx_mod._project = None


def teardown_function():
    """Clean up test project."""
    from claude_code_orchestrate import ctx
    try:
        ctx.rm("", recursive=True)
    except Exception:
        pass


def test_put_get_roundtrip():
    from claude_code_orchestrate import ctx
    ctx.init("test-integration")
    ctx.put("greeting", "hello world")
    result = ctx.get("greeting")
    assert "hello world" in result


def test_put_hierarchical_and_ls():
    from claude_code_orchestrate import ctx
    ctx.init("test-integration")
    ctx.put("phase-1/findings", "found bugs")
    ctx.put("phase-1/decisions", "fix them")
    keys = ctx.ls("phase-1/")
    assert "findings" in keys
    assert "decisions" in keys


def test_search_finds_content():
    from claude_code_orchestrate import ctx
    ctx.init("test-integration")
    ctx.put("notes", "the token refresh mechanism is broken")
    result = ctx.search("token refresh")
    assert "token refresh" in result


def test_rm_removes_key():
    from claude_code_orchestrate import ctx
    ctx.init("test-integration")
    ctx.put("temp", "temporary data")
    ctx.rm("temp")
    try:
        ctx.get("temp")
        assert False, "Should have raised"
    except Exception:
        pass


def test_rm_recursive():
    from claude_code_orchestrate import ctx
    ctx.init("test-integration")
    ctx.put("dir/a", "aaa")
    ctx.put("dir/b", "bbb")
    ctx.rm("dir", recursive=True)
    keys = ctx.ls()
    assert "dir" not in keys
```

- [ ] **Step 2: Run integration tests**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_context_integration.py -v -m integration`
Expected: 5 tests PASS (auto-starts openviking-server if needed)

- [ ] **Step 3: Commit**

```bash
git add tests/test_context_integration.py
git commit -m "test: integration tests for ctx module with live OpenViking"
```

---

### Task 6: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add ctx section to README**

After the existing "All tools" section, add:

```markdown
## Context Management

Persistent, project-scoped context store backed by [OpenViking](https://github.com/volcengine/OpenViking). Requires `pip install openviking`.

```python
from claude_code_orchestrate import Agent, Glob, Read, ctx

ctx.init("my-project")

# Store agent results
result = Agent(description="Research", prompt="Analyze the auth system")
ctx.put("analysis", result)

# Retrieve later — even from a different script
analysis = ctx.get("analysis")

# List what's stored
keys = ctx.ls()  # ["analysis"]

# Search across all context
hits = ctx.search("token refresh")

# Clean up
ctx.rm("analysis")
```

Auto-starts `openviking-server` if not running. All context persists across sessions.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add ctx usage to README"
```
