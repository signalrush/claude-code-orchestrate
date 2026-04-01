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
