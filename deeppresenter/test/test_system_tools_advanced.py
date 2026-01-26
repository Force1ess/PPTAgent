"""
Test advanced system tools usage.
"""

import pytest


class TestSystemToolsAdvanced:
    """Test advanced system tools usage."""

    @pytest.mark.asyncio
    async def test_ripgrep_complex_search(self, agent_env, workspace, tool_call_helper):
        """Test ripgrep: search across multiple files with patterns."""
        # Create multiple Python files with various patterns
        files_content = {
            "模块1.py": """
# Configuration file
API_KEY = "test_key_123"
DEBUG = True
VERSION = "1.0.0"

def 初始化():
    print("初始化模块1")
    return API_KEY
""",
            "模块2.py": """
# Utility functions
import requests

API_KEY = "test_key_456"
BASE_URL = "https://api.example.com"

def 获取数据(api_key=None):
    if api_key is None:
        api_key = API_KEY
    print(f"使用密钥: {api_key}")
""",
            "配置.py": """
# Global configuration
DATABASE_URL = "postgresql://localhost/db"
API_KEY = "prod_key_789"
SECRET_KEY = "secret_value"

配置字典 = {
    "调试模式": False,
    "日志级别": "INFO"
}
""",
        }

        # Write all files
        for filename, content in files_content.items():
            write_call = tool_call_helper(
                "write_file",
                {"path": str(workspace / filename), "content": content},
            )
            await agent_env.tool_execute(write_call)

        # Test 1: Search for API_KEY pattern
        search_call1 = tool_call_helper(
            "execute_command",
            {"command": f"cd {workspace} && rg 'API_KEY' --color never"},
        )
        result1 = await agent_env.tool_execute(search_call1)
        assert not result1.is_error, f"ripgrep failed: {result1.text}"
        assert "API_KEY" in result1.text
        # Should find at least 3 occurrences across files
        assert result1.text.count("API_KEY") >= 3

        # Test 2: Search for chinese patterns
        search_call2 = tool_call_helper(
            "execute_command",
            {"command": f"cd {workspace} && rg '初始化|配置' --color never"},
        )
        result2 = await agent_env.tool_execute(search_call2)
        assert not result2.is_error
        assert "初始化" in result2.text or "配置" in result2.text

        # Test 3: Count matches
        search_call3 = tool_call_helper(
            "execute_command",
            {"command": f"cd {workspace} && rg 'def ' --count --color never"},
        )
        result3 = await agent_env.tool_execute(search_call3)
        assert not result3.is_error
        # Should find function definitions
