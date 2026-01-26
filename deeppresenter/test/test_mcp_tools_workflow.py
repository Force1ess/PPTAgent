"""
Test MCP tools with a complete workflow.
"""

import pytest


class TestMCPToolsWorkflow:
    """Test MCP tools with a complete workflow."""

    @pytest.mark.asyncio
    async def test_complete_workflow_with_chinese(
        self, agent_env, workspace, tool_call_helper
    ):
        """Test complete workflow: nested dirs + write + edit + move + read (with chinese)."""
        # Step 1: Create nested directory structure
        create_dir = tool_call_helper(
            "create_directory",
            {"path": str(workspace / "项目" / "源代码")},
        )
        await agent_env.tool_execute(create_dir)

        create_backup = tool_call_helper(
            "create_directory",
            {"path": str(workspace / "项目" / "备份")},
        )
        await agent_env.tool_execute(create_backup)

        # Step 2: Write initial file with chinese content
        write_call = tool_call_helper(
            "write_file",
            {
                "path": str(workspace / "项目" / "源代码" / "应用.py"),
                "content": "# Version 1.0\n# Author: Test\nprint('你好，世界！')\n",
            },
        )
        write_result = await agent_env.tool_execute(write_call)
        assert not write_result.is_error

        # Step 3: Edit the file (multiple replacements)
        edit_call = tool_call_helper(
            "edit_file",
            {
                "file_path": str(workspace / "项目" / "源代码" / "应用.py"),
                "old_string": "Version 1.0",
                "new_string": "Version 2.0",
            },
        )
        edit_result = await agent_env.tool_execute(edit_call)
        assert not edit_result.is_error

        # Step 4: Append more content
        append_call = tool_call_helper(
            "write_file",
            {
                "path": str(workspace / "项目" / "源代码" / "应用.py"),
                "content": "\n# New feature\nprint('新版本发布')\n",
                "mode": "append",
            },
        )
        await agent_env.tool_execute(append_call)

        # Step 5: Move to backup with new name
        move_call = tool_call_helper(
            "move_file",
            {
                "source": str(workspace / "项目" / "源代码" / "应用.py"),
                "destination": str(workspace / "项目" / "备份" / "应用_v2.0.py"),
            },
        )
        move_result = await agent_env.tool_execute(move_call)
        assert not move_result.is_error

        # Step 6: Verify final state with list_directory
        list_backup = tool_call_helper(
            "list_directory",
            {"path": str(workspace / "项目" / "备份")},
        )
        list_result = await agent_env.tool_execute(list_backup)
        assert "应用_v2.0.py" in list_result.text

        # Step 7: Verify content with read_file
        read_call = tool_call_helper(
            "read_file",
            {"path": str(workspace / "项目" / "备份" / "应用_v2.0.py")},
        )
        read_result = await agent_env.tool_execute(read_call)
        assert "Version 2.0" in read_result.text
        assert "新版本发布" in read_result.text
        assert "你好，世界！" in read_result.text
