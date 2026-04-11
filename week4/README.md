# Week 4 — MCP Server Integration

**Status:** Coming soon (planned for Days 15–18)

## Goal

Expose the AppMentor knowledge base and agent as an MCP (Model Context Protocol) server so it can be used as a tool by Claude Desktop and other MCP clients.

## Planned files

```
week4/
├── mcp_server.py     ← FastMCP server exposing kb_search and agent_query tools
├── client_test.py    ← smoke test using the MCP Python client
└── README.md
```

## Running (once implemented)

```bash
# Start the MCP server
python week4/mcp_server.py

# In Claude Desktop, add the server to mcp_servers config and ask:
# "Search the AppMentor KB for expense claim steps"
```
