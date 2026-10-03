# MCP-Telecom Usage Examples

## Conversational Examples with Claude

Once configured, you can ask Claude natural language questions about your network:

### Basic Device Queries

> "What devices do I have configured?"

> "Show me the BGP summary on nokia-pe1"

> "What's the system info on cisco-xr1?"

### Troubleshooting

> "Check if all my devices are reachable"

> "Troubleshoot BGP on nokia-pe1 — some peers seem to be down"

> "Show me the interface errors on cisco-xr1 interface GigabitEthernet0/0/0"

### Monitoring

> "Are there any active alarms on nokia-pe1?"

> "What's the CPU and memory usage on all my Nokia routers?"

> "Show me the NTP sync status on juniper-mx1"

### Configuration Management

> "Backup the running config on cisco-xr1"

> "Compare the current config on nokia-pe1 with yesterday's backup"

### Multi-Device Operations

> "Compare the BGP state between nokia-pe1 and nokia-pe2"

> "Run a health audit on all my devices"

### Advanced Queries

> "What MPLS LSPs are active on nokia-pe1?"

> "Show me the LLDP neighbors on cisco-sw1 — I need to verify the physical topology"

> "What OSPF neighbors does juniper-mx1 have?"

## Programmatic Usage

You can also use MCP-Telecom programmatically:

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "mcp-telecom"],
        env={"MCP_TELECOM_DEVICES_FILE": "devices.yaml"},
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List available tools
            tools = await session.list_tools()
            print(f"Available tools: {len(tools.tools)}")

            # Call a tool
            result = await session.call_tool(
                "show_bgp_summary",
                arguments={"device": "nokia-pe1"},
            )
            print(result.content[0].text)

asyncio.run(main())
```
