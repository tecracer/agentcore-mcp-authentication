#!/usr/bin/env python3
"""
Local MCP Client for Testing

This module provides a local testing client for the MCP server.
It connects to a locally running MCP server and lists available tools.

Usage:
    python blogpost_mcp_client.py

Prerequisites:
    - MCP server must be running locally on localhost:8000
    - Run 'python blogpost_mcp_server.py' in another terminal first
"""

import asyncio
from datetime import timedelta

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    mcp_url = "http://localhost:8000/mcp"
    headers = {}

    async with streamablehttp_client(mcp_url, headers, timeout=timedelta(seconds=120), terminate_on_close=False) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tool_result = await session.list_tools()
            print("Available tools:")
            for tool in tool_result.tools:
                print(f"  - {tool.name}: {tool.description}")

if __name__ == "__main__":
    asyncio.run(main())
