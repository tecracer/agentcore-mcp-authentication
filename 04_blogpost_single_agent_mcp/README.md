# Blog Post: Single Agent MCP Deployment Guide

This guide explains how to deploy a single MCP agent with OAuth2 authentication to Amazon Bedrock AgentCore Runtime using the **HTTP protocol** approach. This is a blog post example demonstrating the complete workflow.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Deployment Steps](#deployment-steps)
- [Agent Implementation](#agent-implementation)
- [Authentication Setup](#authentication-setup)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Dependencies

Create a `requirements.txt`:

```txt
bedrock-agentcore
bedrock-agentcore-starter-toolkit
mcp>=1.0.0
fastmcp>=0.1.0
starlette>=0.27.0
httpx>=0.25.0
boto3>=1.34.0
requests>=2.31.0
click>=8.0.0
pyyaml>=6.0.0
python-dotenv
```

### Installation

```bash
# Using uv (recommended)
uv pip install -r requirements.txt

# Or using pip
pip install -r requirements.txt
```

### AWS Configuration

Ensure your AWS credentials are configured:

```bash
aws configure
# Or set environment variables
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=eu-central-1
```

## Deployment Steps

### Step 1: Test Locally

Before deploying to the cloud, test your agent locally:

```bash
# Start your agent locally
python blogpost_single_agent_mcp.py
```

In another terminal, test the local endpoint:

```bash
# Test local agent
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello!"}'
```

This ensures your agent works correctly before cloud deployment.

### Step 2: Configure Your Agent

```bash
agentcore configure -e blogpost_single_agent_mcp.py --protocol HTTP -n blogpost_single_agent_mcp
```

This command:

- Creates `.bedrock_agentcore.yaml` configuration file
- Sets up IAM execution role (if needed)
- Configures ECR repository (if needed)
- Defines your agent's entry point with HTTP protocol
- Configures OAuth2 authentication

### Step 3: Deploy to Cloud

```bash
agentcore launch
```

This command:

- Builds your container using AWS CodeBuild (ARM64 architecture)
- Creates AWS resources (first time only):
  - IAM execution role with required permissions
  - ECR repository for container images
  - CodeBuild project for future builds
- Deploys your agent to AgentCore Runtime with OAuth2 authentication
- Sets up CloudWatch logging
- Returns agent ARN for testing

### Step 4: Test Your Deployed Agent

```bash
# Test with authentication
agentcore invoke "What is 2+2?"
```

### Step 5: Check Status (Optional)

```bash
agentcore status
```

## Agent Implementation

Your agent implementation (`single_agent_mcp.py`):

```python
import asyncio
import logging
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.decorators import requires_access_token
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from datetime import timedelta
import boto3

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

def get_ssm_parameter(parameter_name: str, decrypt: bool = True) -> str:
    """Retrieve a parameter from AWS Systems Manager Parameter Store."""
    try:
        ssm_client = boto3.client('ssm')
        response = ssm_client.get_parameter(
            Name=parameter_name,
            WithDecryption=decrypt
        )
        return response['Parameter']['Value']
    except Exception as e:
        raise ValueError(f"Failed to retrieve SSM parameter {parameter_name}: {str(e)}")

@requires_access_token(
    provider_name=get_ssm_parameter("/app/mcp/single_agent_mcp/cognito_provider"),
    scopes=[],
    auth_flow="M2M",
)
async def single_agent_mcp_bedrock(payload, access_token: str):
    """
    Main agent function that connects to MCP server and processes requests.
    Uses OAuth2 access token for authentication.
    """
    try:
        # Get OAuth2 configuration from SSM
        logger.info("Retrieving OAuth2 configuration...")
        client_id = get_ssm_parameter("/app/mcp/single_agent_mcp/machine_client_id")
        client_secret = get_ssm_parameter("/app/mcp/single_agent_mcp/cognito_secret")
        discovery_url = get_ssm_parameter("/app/mcp/single_agent_mcp/cognito_discovery_url")

        # Connect to MCP server
        mcp_server_arn = "your-mcp-server-arn-here"
        region = "eu-central-1"
        encoded_arn = mcp_server_arn.replace(":", "%3A").replace("/", "%2F")
        mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

        headers = {
            "authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Connect to MCP server
        async with streamablehttp_client(
            mcp_url,
            headers,
            timeout=timedelta(seconds=30)
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                # Get user input
                user_input = payload.get("input", "Hello")

                # List available tools
                tools = await session.list_tools()
                logger.info(f"Available tools: {[tool.name for tool in tools.tools]}")

                # For demonstration, just return available tools
                tool_list = [f"{tool.name}: {tool.description}" for tool in tools.tools]

                return {
                    "message": f"User input: {user_input}",
                    "available_tools": tool_list,
                    "status": "success"
                }

    except Exception as e:
        logger.error(f"Error in agent execution: {str(e)}")
        return {
            "error": str(e),
            "status": "error"
        }

@app.entrypoint
async def main_handler(payload):
    """Main entrypoint for the agent."""
    return await single_agent_mcp_bedrock(payload)

if __name__ == "__main__":
    app.run()
```

## Authentication Setup

### OAuth2 Flow

This implementation uses OAuth2 Machine-to-Machine (M2M) authentication:

1. **Cognito Setup**: Creates User Pool, Resource Server, and M2M client
2. **SSM Storage**: Stores all credentials securely in Parameter Store
3. **Runtime Authentication**: Agent automatically retrieves and uses access tokens
4. **MCP Connection**: Uses Bearer token to connect to deployed MCP servers

### SSM Parameters

The setup creates these parameters under `/app/mcp/single_agent_mcp/`:

- `userpool_id` - Cognito User Pool ID
- `machine_client_id` - M2M Client ID
- `cognito_secret` - M2M Client Secret
- `cognito_discovery_url` - OAuth2 discovery endpoint
- `cognito_provider` - AgentCore OAuth2 provider name
- `cognito_auth_url` - Authorization URL
- `cognito_token_url` - Token endpoint URL
- `cognito_auth_scope` - OAuth2 scopes

## Troubleshooting

### Common Issues

1. **Authentication Errors**

   ```bash
   # Check AWS credentials
   aws sts get-caller-identity
   ```

2. **SSM Parameter Issues**

   ```bash
   # Check if parameters exist
   aws ssm get-parameters-by-path --path "/app/mcp/single_agent_mcp/" --recursive
   ```

3. **OAuth2 Provider Issues**

   ```bash
   # Check AgentCore OAuth2 providers
   aws bedrock-agentcore list-oauth2-credential-providers
   ```

4. **MCP Connection Failures**

   - Verify MCP server is deployed and accessible
   - Check Bearer token validity
   - Ensure proper URL encoding of ARN

### Debug Commands

```bash
# Check agent status
agentcore status

# View logs
aws logs describe-log-groups --log-group-name-prefix /aws/bedrock/agentcore

# Test locally
python blogpost_single_agent_mcp.py

# Debug OAuth2 configuration
python -c "from single_agent_mcp import debug_oauth2_config; import asyncio; asyncio.run(debug_oauth2_config())"
```

### Cleanup

To clean up all resources:

```bash
# Delete AgentCore resources
agentcore delete --confirm
```

---
