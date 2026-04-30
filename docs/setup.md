# ADHD Setup

## Install

```bash
cd adhd
uv pip install -e .
```

## Join the Shared Bus

```bash
export ADHD_BUS_REPO_SLUG=projects
```

Add to your shell profile or set in every terminal that coordinates with other
agents.

## MCP Server

```json
{
  "mcpServers": {
    "adhd": {
      "command": "bash",
      "args": [
        "-c",
        "ADHD_BUS_REPO_SLUG=projects uv --directory /home/mrrobot0985/work/projects/adhd run adhd-mcp"
      ]
    }
  }
}
```

## Claim Main Coordinator

```python
import adhd.bus as bus
result = bus.claim_main()
print(result.success, result.message)
```

Full workspace guide: `../SETUP.md`
