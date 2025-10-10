# Blog Post: MCP Server Deployment - Complete 5-Step Workflow

## The 5-Step MCP Deployment Workflow

Based on the [official AWS documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html), this guide walks you through the exact 5-step sequence to deploy your MCP server to Amazon Bedrock AgentCore Runtime. This is a blog post example demonstrating the complete workflow with blogpost-specific naming to avoid conflicts with existing resources.

## Configurable MCP Server Names

**Important:** All scripts now support configurable MCP server names! Replace `your_mcp_server_name` with your chosen name throughout this guide.

**Examples of MCP server names:**

- `mcp_simple_calculator` (default example)
- `weather_service`
- `financial_calculator`
- `travel_assistant`

**Benefits:**

- Deploy multiple MCP servers with different names
- Shared Cognito infrastructure (User Pool, Resource Server, Domain)
- Individual credentials per MCP server stored in SSM

---

## Step 1: Set Up Cognito Authentication

**Execute the Cognito setup script first:**

```bash
python setup_M2M_cognito.py setup --mcp-name your_mcp_server_name
```

**Example:**

```bash
python setup_M2M_cognito.py setup --mcp-name mcp_simple_calculator
```

This creates:

- Cognito User Pool with M2M client
- Resource server with scopes
- Cognito domain for OAuth2
- Stores all credentials in AWS SSM

**CRITICAL:** Save the printed Discovery URL and Machine Client ID - you'll need them in Step 3!

The script will output something like:

```
IMPORTANT - Save These for AgentCore Configuration:
============================================================
Discovery URL: https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_ABC123DEF/.well-known/openid-configuration
Machine Client ID: 1a2b3c4d5e6f7g8h9i0j
============================================================
```

---

## Step 2: Test Server Locally

**Test your MCP server implementation locally:**

```bash
# Terminal 1: Start the MCP server
python blogpost_mcp_server.py

# Terminal 2: Test with local client
python blogpost_mcp_client.py
```

Your `blogpost_mcp_server.py` should follow this structure:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(host="0.0.0.0", stateless_http=True)

@mcp.tool()
def your_tool(param: str) -> str:
    """Your tool description"""
    return "result"

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

---

## Step 3: Configure AgentCore

**Configure your agent for deployment:**

```bash
agentcore configure --name your_mcp_server_name --protocol MCP --entrypoint blogpost_mcp_server.py
```

**Example:**

```bash
agentcore configure --name blogpost_mcp_simple_calculator --protocol MCP --entrypoint blogpost_mcp_server.py
```

During the guided setup:

1. **Execution Role**: Provide an IAM role with bedrock:InvokeModel permissions
2. **ECR Repository**: Press Enter to auto-create
3. **Dependencies**: Auto-detected from `requirements.txt`
4. **OAuth Configuration**:
   - Answer `yes` when asked about OAuth
   - **Discovery URL**: Use the URL from Step 1
   - **Client ID**: Use the Machine Client ID from Step 1

---

## Step 4: Deploy to Cloud

**Launch your agent to AWS:**

```bash
agentcore launch
```

This command will:

1. Build a Docker container with your MCP server
2. Push it to Amazon ECR
3. Create an Amazon Bedrock AgentCore runtime
4. Deploy your agent to AWS

After deployment, you'll receive an agent runtime ARN:

```
arn:aws:bedrock-agentcore:eu-central-1:123456789012:runtime/your_mcp_server_name-xyz123
```

**Example:**

```
arn:aws:bedrock-agentcore:eu-central-1:123456789012:runtime/mcp_simple_calculator-xyz123
```

---

## Step 5: Test Deployed Server

**Test your deployed MCP server with authentication:**

```bash
python blogpost_invoke_mcp_tools.py --name your_mcp_server_name
```

**Example:**

```bash
python blogpost_invoke_mcp_tools.py --name blogpost_mcp_simple_calculator
```

This script will:

- Load your agent ARN from `.bedrock_agentcore.yaml`
- Get Bearer token from Cognito (using stored SSM parameters)
- Connect to your deployed MCP server
- List and test all available tools

Expected output:

```
Successfully connected to MCP server!
Found 3 tools available.

Testing MCP Tools:
==================================================

Testing add_numbers(5, 3)...
   Result: 8

Testing multiply_numbers(4, 7)...
   Result: 28

Testing greet_user('Alice')...
   Result: Hello, Alice! Nice to meet you.

MCP tool testing completed!
All tools are working correctly!
```

---

## Key Configuration Details

### MCP Server Requirements

- **Host**: `0.0.0.0` (required for container deployment)
- **Port**: `8000` (AgentCore Runtime default)
- **Endpoint**: `/mcp` (AgentCore Runtime expects this path)
- **Transport**: `streamable-http` (required for AgentCore Runtime)
- **Stateless**: `True` (required for session isolation)

### Authentication Flow

- **Machine-to-Machine (M2M)**: OAuth2 client credentials flow
- **Bearer Token**: Generated from Cognito using stored credentials
- **Session Isolation**: Automatic via `Mcp-Session-Id` header
- **SSM Parameter Store**: Securely stores all credentials with `/app/blogpost/mcp/` prefix to avoid conflicts

### URL Encoding

The `blogpost_invoke_mcp_tools.py` script automatically handles URL encoding of the agent runtime ARN:

- Colons (`:`) become `%3A`
- Forward slashes (`/`) become `%2F`

---

## Troubleshooting

### Common Issues

**Step 1 - Cognito Setup Fails:**

```bash
aws sts get-caller-identity
aws configure list
```

**Step 2 - Local Test Fails:**

```bash
netstat -an | grep 8000
curl http://localhost:8000/mcp
```

**Step 3 - AgentCore Configure Issues:**

- Ensure you have the correct Discovery URL and Client ID from Step 1
- Verify your execution role has `bedrock:InvokeModel` permissions

**Step 4 - Launch Fails:**

```bash
agentcore status
agentcore logs
```

**Step 5 - Remote Test Fails:**

- Verify agent ARN in `.bedrock_agentcore.yaml`
- Check CloudWatch logs: `/aws/bedrock-agentcore/runtimes/{agent_id}/runtime-logs`
- Ensure container started successfully

### Cleanup

To clean up all resources:

```bash
# Delete Cognito resources for specific MCP server
python setup_M2M_cognito.py cleanup --mcp-name your_mcp_server_name --confirm

# Delete AgentCore resources
agentcore delete --confirm
```

**Example:**

```bash
# Delete Cognito resources for mcp_simple_calculator
python setup_M2M_cognito.py cleanup --mcp-name mcp_simple_calculator --confirm
```

---

## Workflow Benefits

Now you have the complete power of the dark side... I mean, the complete 5-step MCP deployment workflow!

## Complete Workflow Example

Here's a complete example deploying a weather service MCP server:

```bash
# Step 1: Set up Cognito for weather service
python setup_M2M_cognito.py setup --mcp-name weather_service

# Step 2: Test locally (same for all MCP servers)
python blogpost_mcp_client.py

# Step 3: Configure AgentCore
agentcore configure --name weather_service --protocol MCP --entrypoint blogpost_mcp_server.py
# (Use Discovery URL and Client ID from Step 1)

# Step 4: Deploy to cloud
agentcore launch

# Step 5: Test deployed server
python blogpost_invoke_mcp_tools.py --name weather_service

# Later: Clean up resources
python setup_M2M_cognito.py cleanup --mcp-name weather_service --confirm
agentcore delete --confirm
```

## Multiple MCP Servers

You can deploy multiple MCP servers that share the same Cognito infrastructure:

```bash
# Deploy first MCP server
python setup_M2M_cognito.py setup --mcp-name weather_service
agentcore configure --name weather_service --protocol MCP --entrypoint blogpost_mcp_server.py
agentcore launch
python blogpost_invoke_mcp_tools.py --name weather_service

# Deploy second MCP server (reuses Cognito infrastructure!)
python setup_M2M_cognito.py setup --mcp-name financial_calculator
agentcore configure --name financial_calculator --protocol MCP --entrypoint blogpost_mcp_server.py
agentcore launch
python blogpost_invoke_mcp_tools.py --name financial_calculator
```
