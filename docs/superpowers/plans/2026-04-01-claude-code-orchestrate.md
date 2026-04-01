# claude-code-orchestrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python SDK that connects to `claude mcp serve` and exposes all 22 Claude Code tools as callable Python functions.

**Architecture:** Singleton MCP transport auto-spawns `claude mcp serve` on first tool call, communicates via JSON-RPC 2.0 over stdio, and cleans up on process exit. Each tool is a module-level function with signatures matching Claude Code's exact parameter names.

**Tech Stack:** Python 3.10+, stdlib only (subprocess, json, atexit)

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `claude_code_orchestrate/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```python
# pyproject.toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "claude-code-orchestrate"
version = "0.1.0"
description = "Python SDK for Claude Code CLI tools via MCP"
requires-python = ">=3.10"
license = "MIT"

[project.urls]
Repository = "https://github.com/tianhaowu/claude-code-orchestrate"
```

- [ ] **Step 2: Create empty __init__.py**

```python
# claude_code_orchestrate/__init__.py
```

Leave empty for now — will add re-exports in Task 4.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml claude_code_orchestrate/__init__.py
git commit -m "chore: project scaffolding"
```

---

### Task 2: MCP Transport Layer

**Files:**
- Create: `claude_code_orchestrate/mcp_transport.py`
- Create: `tests/test_transport.py`

- [ ] **Step 1: Write failing test for MCPTransport initialization**

```python
# tests/test_transport.py
import subprocess
from unittest.mock import patch, MagicMock
from claude_code_orchestrate.mcp_transport import MCPTransport, ClaudeCodeError


def _mock_popen(responses: list[str]):
    """Create a mock Popen that returns pre-canned JSON-RPC responses."""
    proc = MagicMock()
    proc.stdin = MagicMock()
    proc.stdout = MagicMock()
    proc.stdout.readline = MagicMock(side_effect=[
        (r + "\n").encode() for r in responses
    ])
    proc.poll = MagicMock(return_value=None)
    proc.pid = 12345
    return proc


def test_start_sends_initialize_handshake():
    init_response = '{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"claude","version":"1.0"}}}'
    tools_response = '{"jsonrpc":"2.0","id":2,"result":{"tools":[]}}'

    with patch("subprocess.Popen", return_value=_mock_popen([init_response, tools_response])) as mock_popen:
        transport = MCPTransport()
        transport.start()

        mock_popen.assert_called_once()
        args = mock_popen.call_args
        assert args[0][0] == ["claude", "mcp", "serve"]

        # Should have written initialize request + notification + tools/list
        assert transport._proc.stdin.write.call_count == 3
        transport.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_transport.py::test_start_sends_initialize_handshake -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_code_orchestrate.mcp_transport'`

- [ ] **Step 3: Implement MCPTransport**

```python
# claude_code_orchestrate/mcp_transport.py
import json
import subprocess


class ClaudeCodeError(Exception):
    """Raised when a tool call fails."""
    def __init__(self, tool_name: str, message: str):
        self.tool_name = tool_name
        super().__init__(f"{tool_name}: {message}")


class MCPTransport:
    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._request_id = 0
        self._tools: list[dict] = []

    def start(self) -> None:
        self._proc = subprocess.Popen(
            ["claude", "mcp", "serve"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        # Initialize handshake
        init_result = self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "claude-code-orchestrate", "version": "0.1.0"},
        })
        # Send initialized notification (no response expected)
        self._send_notification("notifications/initialized", {})
        # Discover tools
        tools_result = self._send("tools/list", {})
        self._tools = tools_result.get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> str:
        result = self._send("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            text = result.get("content", [{}])[0].get("text", "Unknown error")
            raise ClaudeCodeError(name, text)
        content = result.get("content", [])
        return content[0].get("text", "") if content else ""

    def list_tools(self) -> list[dict]:
        return self._tools

    def stop(self) -> None:
        if self._proc:
            self._proc.stdin.close()
            self._proc.stdout.close()
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
            self._proc = None

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _send(self, method: str, params: dict) -> dict:
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }
        self._write(req)
        return self._read_response(req["id"])

    def _send_notification(self, method: str, params: dict) -> None:
        # Notifications have no id and expect no response
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        self._write(msg)

    def _write(self, msg: dict) -> None:
        line = json.dumps(msg) + "\n"
        self._proc.stdin.write(line.encode())
        self._proc.stdin.flush()

    def _read_response(self, expected_id: int) -> dict:
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise ClaudeCodeError("transport", "MCP server closed unexpectedly")
            data = json.loads(line)
            # Skip notifications (no id field)
            if "id" not in data:
                continue
            if data["id"] == expected_id:
                if "error" in data:
                    err = data["error"]
                    raise ClaudeCodeError("transport", f"JSON-RPC error {err.get('code')}: {err.get('message')}")
                return data.get("result", {})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_transport.py::test_start_sends_initialize_handshake -v`
Expected: PASS

- [ ] **Step 5: Write test for call_tool**

```python
# append to tests/test_transport.py

def test_call_tool_returns_text_content():
    init_response = '{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"claude","version":"1.0"}}}'
    tools_response = '{"jsonrpc":"2.0","id":2,"result":{"tools":[]}}'
    tool_result = '{"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"file contents here"}]}}'

    proc = _mock_popen([init_response, tools_response, tool_result])
    with patch("subprocess.Popen", return_value=proc):
        transport = MCPTransport()
        transport.start()
        result = transport.call_tool("Read", {"file_path": "/tmp/test.txt"})
        assert result == "file contents here"
        transport.stop()


def test_call_tool_raises_on_error():
    init_response = '{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"claude","version":"1.0"}}}'
    tools_response = '{"jsonrpc":"2.0","id":2,"result":{"tools":[]}}'
    error_result = '{"jsonrpc":"2.0","id":3,"result":{"isError":true,"content":[{"type":"text","text":"file not found"}]}}'

    proc = _mock_popen([init_response, tools_response, error_result])
    with patch("subprocess.Popen", return_value=proc):
        transport = MCPTransport()
        transport.start()
        try:
            transport.call_tool("Read", {"file_path": "/nonexistent"})
            assert False, "Should have raised"
        except ClaudeCodeError as e:
            assert "file not found" in str(e)
            assert e.tool_name == "Read"
        transport.stop()
```

- [ ] **Step 6: Run all transport tests**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_transport.py -v`
Expected: 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add claude_code_orchestrate/mcp_transport.py tests/test_transport.py
git commit -m "feat: MCP transport layer with JSON-RPC stdio communication"
```

---

### Task 3: Client Tool Functions

**Files:**
- Create: `claude_code_orchestrate/client.py`
- Create: `tests/test_client.py`

- [ ] **Step 1: Write failing test for singleton transport and Read function**

```python
# tests/test_client.py
from unittest.mock import patch, MagicMock
import claude_code_orchestrate.client as client_mod


def _mock_transport():
    transport = MagicMock()
    transport.call_tool = MagicMock(return_value="mock result")
    return transport


def setup_function():
    """Reset singleton before each test."""
    client_mod._transport = None


def test_read_calls_transport_with_correct_args():
    transport = _mock_transport()
    with patch.object(client_mod, "_transport", transport):
        from claude_code_orchestrate.client import Read
        result = Read(file_path="/tmp/test.py")
        transport.call_tool.assert_called_once_with("Read", {"file_path": "/tmp/test.py"})
        assert result == "mock result"


def test_read_strips_none_optional_args():
    transport = _mock_transport()
    with patch.object(client_mod, "_transport", transport):
        from claude_code_orchestrate.client import Read
        Read(file_path="/tmp/test.py", offset=None, limit=10)
        transport.call_tool.assert_called_once_with("Read", {"file_path": "/tmp/test.py", "limit": 10})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_code_orchestrate.client'`

- [ ] **Step 3: Implement client.py with all 22 tool functions**

```python
# claude_code_orchestrate/client.py
import atexit
from claude_code_orchestrate.mcp_transport import MCPTransport

_transport: MCPTransport | None = None


def _get_transport() -> MCPTransport:
    global _transport
    if _transport is None:
        _transport = MCPTransport()
        _transport.start()
        atexit.register(_transport.stop)
    return _transport


def _call(tool_name: str, **kwargs) -> str:
    args = {k: v for k, v in kwargs.items() if v is not None}
    return _get_transport().call_tool(tool_name, args)


# --- File Tools ---

def Read(file_path: str, offset: int = None, limit: int = None, pages: str = None) -> str:
    return _call("Read", file_path=file_path, offset=offset, limit=limit, pages=pages)


def Write(file_path: str, content: str) -> str:
    return _call("Write", file_path=file_path, content=content)


def Edit(file_path: str, old_string: str, new_string: str, replace_all: bool = None) -> str:
    return _call("Edit", file_path=file_path, old_string=old_string, new_string=new_string, replace_all=replace_all)


def Glob(pattern: str, path: str = None) -> str:
    return _call("Glob", pattern=pattern, path=path)


def Grep(pattern: str, path: str = None, glob: str = None, output_mode: str = None,
         type: str = None, head_limit: int = None, offset: int = None,
         multiline: bool = None, context: int = None) -> str:
    return _call("Grep", pattern=pattern, path=path, glob=glob, output_mode=output_mode,
                 type=type, head_limit=head_limit, offset=offset, multiline=multiline, context=context)


# --- Execution ---

def Bash(command: str, timeout: int = None, description: str = None) -> str:
    return _call("Bash", command=command, timeout=timeout, description=description)


# --- Agent Orchestration ---

def Agent(description: str, prompt: str, subagent_type: str = None, model: str = None,
          run_in_background: bool = None, name: str = None, team_name: str = None,
          mode: str = None, isolation: str = None) -> str:
    return _call("Agent", description=description, prompt=prompt, subagent_type=subagent_type,
                 model=model, run_in_background=run_in_background, name=name,
                 team_name=team_name, mode=mode, isolation=isolation)


def SendMessage(to: str, message: str, summary: str = None) -> str:
    return _call("SendMessage", to=to, message=message, summary=summary)


def TaskOutput(task_id: str, block: bool = None, timeout: int = None) -> str:
    return _call("TaskOutput", task_id=task_id, block=block, timeout=timeout)


def TaskStop(task_id: str = None, shell_id: str = None) -> str:
    return _call("TaskStop", task_id=task_id, shell_id=shell_id)


# --- Web ---

def WebFetch(url: str, prompt: str) -> str:
    return _call("WebFetch", url=url, prompt=prompt)


def WebSearch(query: str, allowed_domains: list = None, blocked_domains: list = None) -> str:
    return _call("WebSearch", query=query, allowed_domains=allowed_domains, blocked_domains=blocked_domains)


# --- Scheduling ---

def CronCreate(cron: str, prompt: str, recurring: bool = None, durable: bool = None) -> str:
    return _call("CronCreate", cron=cron, prompt=prompt, recurring=recurring, durable=durable)


def CronDelete(id: str) -> str:
    return _call("CronDelete", id=id)


def CronList() -> str:
    return _call("CronList")


# --- Teams ---

def TeamCreate(team_name: str, description: str = None, agent_type: str = None) -> str:
    return _call("TeamCreate", team_name=team_name, description=description, agent_type=agent_type)


def TeamDelete() -> str:
    return _call("TeamDelete")


# --- Remote ---

def RemoteTrigger(action: str, trigger_id: str = None, body: str = None) -> str:
    return _call("RemoteTrigger", action=action, trigger_id=trigger_id, body=body)


# --- Worktree ---

def EnterWorktree(name: str) -> str:
    return _call("EnterWorktree", name=name)


def ExitWorktree(action: str, discard_changes: bool = None) -> str:
    return _call("ExitWorktree", action=action, discard_changes=discard_changes)


# --- Misc ---

def Skill(skill: str, args: str = None) -> str:
    return _call("Skill", skill=skill, args=args)


def ToolSearch(query: str, max_results: int = None) -> str:
    return _call("ToolSearch", query=query, max_results=max_results)


def NotebookEdit(notebook_path: str, new_source: str, cell_id: str = None,
                 cell_type: str = None, edit_mode: str = None) -> str:
    return _call("NotebookEdit", notebook_path=notebook_path, new_source=new_source,
                 cell_id=cell_id, cell_type=cell_type, edit_mode=edit_mode)
```

- [ ] **Step 4: Run tests**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_client.py -v`
Expected: PASS

- [ ] **Step 5: Write tests for Agent and Bash functions**

```python
# append to tests/test_client.py

def test_agent_passes_all_params():
    transport = _mock_transport()
    with patch.object(client_mod, "_transport", transport):
        from claude_code_orchestrate.client import Agent
        Agent(description="fix bugs", prompt="fix all bugs", model="sonnet", run_in_background=True)
        transport.call_tool.assert_called_once_with("Agent", {
            "description": "fix bugs",
            "prompt": "fix all bugs",
            "model": "sonnet",
            "run_in_background": True,
        })


def test_bash_with_timeout():
    transport = _mock_transport()
    with patch.object(client_mod, "_transport", transport):
        from claude_code_orchestrate.client import Bash
        Bash(command="echo hello", timeout=5000)
        transport.call_tool.assert_called_once_with("Bash", {
            "command": "echo hello",
            "timeout": 5000,
        })
```

- [ ] **Step 6: Run all client tests**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_client.py -v`
Expected: 4 tests PASS

- [ ] **Step 7: Commit**

```bash
git add claude_code_orchestrate/client.py tests/test_client.py
git commit -m "feat: 22 tool functions with singleton MCP transport"
```

---

### Task 4: Public API (\_\_init\_\_.py) and Packaging

**Files:**
- Modify: `claude_code_orchestrate/__init__.py`
- Create: `tests/test_init.py`

- [ ] **Step 1: Write failing test for public imports**

```python
# tests/test_init.py
def test_all_tools_importable():
    from claude_code_orchestrate import (
        Read, Write, Edit, Glob, Grep,
        Bash,
        Agent, SendMessage, TaskOutput, TaskStop,
        WebFetch, WebSearch,
        CronCreate, CronDelete, CronList,
        TeamCreate, TeamDelete,
        RemoteTrigger,
        EnterWorktree, ExitWorktree,
        Skill, ToolSearch, NotebookEdit,
        ClaudeCodeError,
    )
    # All 22 tools + error class = 23 names
    assert callable(Read)
    assert callable(Agent)
    assert callable(CronCreate)


def test_all_exports_listed():
    import claude_code_orchestrate
    assert len(claude_code_orchestrate.__all__) == 23
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_init.py -v`
Expected: FAIL — `ImportError: cannot import name 'Read'`

- [ ] **Step 3: Implement __init__.py with re-exports**

```python
# claude_code_orchestrate/__init__.py
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
]
```

- [ ] **Step 4: Run all tests**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Verify package installs**

Run: `cd ~/claude-code-orchestrate && pip install -e .`
Expected: Successfully installed claude-code-orchestrate-0.1.0

- [ ] **Step 6: Commit**

```bash
git add claude_code_orchestrate/__init__.py tests/test_init.py
git commit -m "feat: public API with all 22 tools exported"
```

---

### Task 5: Integration Test with Live MCP Server

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
"""
Integration tests that connect to a real `claude mcp serve` instance.
Run with: pytest tests/test_integration.py -v -m integration
Skip in CI or when claude CLI is not available.
"""
import shutil
import tempfile
import os
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


def test_read_write_roundtrip(tmp_dir):
    from claude_code_orchestrate import Read, Write

    test_file = os.path.join(tmp_dir, "test.txt")
    Write(file_path=test_file, content="hello world")
    result = Read(file_path=test_file)
    assert "hello world" in result


def test_glob_finds_files(tmp_dir):
    from claude_code_orchestrate import Write, Glob

    Write(file_path=os.path.join(tmp_dir, "a.py"), content="# a")
    Write(file_path=os.path.join(tmp_dir, "b.py"), content="# b")
    result = Glob(pattern="*.py", path=tmp_dir)
    assert "a.py" in result
    assert "b.py" in result


def test_bash_runs_command():
    from claude_code_orchestrate import Bash

    result = Bash(command="echo hello_from_sdk")
    assert "hello_from_sdk" in result


def test_grep_finds_pattern(tmp_dir):
    from claude_code_orchestrate import Write, Grep

    Write(file_path=os.path.join(tmp_dir, "search.txt"), content="find_this_needle in haystack")
    result = Grep(pattern="find_this_needle", path=tmp_dir)
    assert "find_this_needle" in result or "search.txt" in result


def test_edit_replaces_string(tmp_dir):
    from claude_code_orchestrate import Write, Read, Edit

    test_file = os.path.join(tmp_dir, "edit_me.txt")
    Write(file_path=test_file, content="old_value here")
    Edit(file_path=test_file, old_string="old_value", new_string="new_value")
    result = Read(file_path=test_file)
    assert "new_value" in result
    assert "old_value" not in result
```

- [ ] **Step 2: Add pytest marker config**

```python
# append to pyproject.toml

[tool.pytest.ini_options]
markers = [
    "integration: tests that require a live claude mcp serve instance",
]
```

- [ ] **Step 3: Run integration tests**

Run: `cd ~/claude-code-orchestrate && python -m pytest tests/test_integration.py -v -m integration`
Expected: 5 tests PASS (requires `claude` CLI on PATH)

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py pyproject.toml
git commit -m "test: integration tests with live MCP server"
```

---

### Task 6: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README**

```markdown
# claude-code-orchestrate

Python SDK that makes every Claude Code CLI tool callable as a Python function.

## Install

```bash
pip install -e .
```

Requires `claude` CLI installed and on PATH.

## Usage

```python
from claude_code_orchestrate import Read, Edit, Glob, Bash, Agent

# File operations
content = Read(file_path="src/main.py")
Edit(file_path="src/main.py", old_string="print(", new_string="logger.info(", replace_all=True)

# Search
files = Glob(pattern="src/**/*.py")
matches = Grep(pattern="TODO", path="src/")

# Shell
output = Bash(command="npm test")

# Sub-agent orchestration
result = Agent(
    description="Fix auth bugs",
    prompt="Find and fix all authentication bugs in src/api/",
)

# Parallel agents
Agent(description="Fix auth", prompt="Fix auth.py", name="a1", run_in_background=True)
Agent(description="Fix tests", prompt="Fix tests/", name="a2", run_in_background=True)
SendMessage(to="a1", message="status?")

# Scheduling
CronCreate(cron="0 9 * * 1", prompt="Review open PRs")
```

Every function name and parameter matches Claude Code's tool signatures exactly.

## How it works

Spawns `claude mcp serve` as a subprocess, communicates via JSON-RPC 2.0 over stdio. Transport is lazily initialized on first call and cleaned up at exit.

## All tools

**File:** `Read`, `Write`, `Edit`, `Glob`, `Grep`
**Execution:** `Bash`
**Agent:** `Agent`, `SendMessage`, `TaskOutput`, `TaskStop`
**Web:** `WebFetch`, `WebSearch`
**Scheduling:** `CronCreate`, `CronDelete`, `CronList`
**Teams:** `TeamCreate`, `TeamDelete`
**Remote:** `RemoteTrigger`
**Worktree:** `EnterWorktree`, `ExitWorktree`
**Misc:** `Skill`, `ToolSearch`, `NotebookEdit`
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with usage examples"
```
