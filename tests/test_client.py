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


def test_read_returns_file_content():
    transport = _mock_transport()
    transport.call_tool = MagicMock(return_value='{"type":"text","file":{"filePath":"/tmp/test.py","content":"print(hello)"}}')
    with patch.object(client_mod, "_transport", transport):
        result = client_mod.Read(file_path="/tmp/test.py")
        assert result == "print(hello)"


def test_glob_returns_list():
    transport = _mock_transport()
    transport.call_tool = MagicMock(return_value='{"filenames":["/a.py","/b.py"],"numFiles":2}')
    with patch.object(client_mod, "_transport", transport):
        result = client_mod.Glob(pattern="*.py")
        assert result == ["/a.py", "/b.py"]


def test_bash_returns_stdout():
    transport = _mock_transport()
    transport.call_tool = MagicMock(return_value='{"stdout":"hello world","stderr":"","interrupted":false}')
    with patch.object(client_mod, "_transport", transport):
        result = client_mod.Bash(command="echo hello world")
        assert result == "hello world"


def test_grep_returns_filenames():
    transport = _mock_transport()
    transport.call_tool = MagicMock(return_value='{"mode":"files_with_matches","filenames":["/a.py"],"numFiles":1}')
    with patch.object(client_mod, "_transport", transport):
        result = client_mod.Grep(pattern="TODO")
        assert result == ["/a.py"]


def test_write_returns_filepath():
    transport = _mock_transport()
    transport.call_tool = MagicMock(return_value='{"type":"create","filePath":"/tmp/new.txt","content":"hi"}')
    with patch.object(client_mod, "_transport", transport):
        result = client_mod.Write(file_path="/tmp/new.txt", content="hi")
        assert result == "/tmp/new.txt"


def test_edit_returns_diff():
    transport = _mock_transport()
    transport.call_tool = MagicMock(return_value='{"structuredPatch":[{"lines":["-old","+new"]}]}')
    with patch.object(client_mod, "_transport", transport):
        result = client_mod.Edit(file_path="/tmp/f.txt", old_string="old", new_string="new")
        assert "-old" in result
        assert "+new" in result
