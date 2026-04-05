def test_all_tools_importable():
    from super_orchestrate import (
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
    # All 23 tools + error class = 24 names
    assert callable(Read)
    assert callable(Agent)
    assert callable(CronCreate)


def test_all_exports_listed():
    import super_orchestrate
    assert len(super_orchestrate.__all__) == 25
