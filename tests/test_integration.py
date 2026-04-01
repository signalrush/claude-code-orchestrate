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
    assert isinstance(result, str)
    assert "hello world" in result


def test_glob_finds_files(tmp_dir):
    from claude_code_orchestrate import Write, Glob

    Write(file_path=os.path.join(tmp_dir, "a.py"), content="# a")
    Write(file_path=os.path.join(tmp_dir, "b.py"), content="# b")
    result = Glob(pattern="*.py", path=tmp_dir)
    assert isinstance(result, list)
    assert any("a.py" in f for f in result)
    assert any("b.py" in f for f in result)


def test_bash_runs_command():
    from claude_code_orchestrate import Bash

    result = Bash(command="echo hello_from_sdk")
    assert result == "hello_from_sdk\n" or result == "hello_from_sdk"


def test_grep_finds_pattern(tmp_dir):
    from claude_code_orchestrate import Write, Grep

    Write(file_path=os.path.join(tmp_dir, "search.txt"), content="find_this_needle in haystack")
    result = Grep(pattern="find_this_needle", path=tmp_dir)
    assert isinstance(result, list)
    assert any("search.txt" in f for f in result)


def test_edit_replaces_string(tmp_dir):
    from claude_code_orchestrate import Write, Read, Edit

    test_file = os.path.join(tmp_dir, "edit_me.txt")
    Write(file_path=test_file, content="old_value here")
    Edit(file_path=test_file, old_string="old_value", new_string="new_value")
    result = Read(file_path=test_file)
    assert isinstance(result, str)
    assert "new_value" in result
    assert "old_value" not in result
