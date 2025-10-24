# Machine-to-Machine (M2M) Authentication for MCP with Bedrock AgentCore

## Quick Start Commands

### 1. Setup Cognito (M2M Authentication)

```bash
cd 03_deploy_mcp
python setup_M2M_cognito.py setup --mcp-name blogpost_mcp_simple_calculator
```

**Save the output values:**

- Discovery URL
- Machine Client ID

### 2. Deploy MCP Server

```bash
agentcore configure --name blogpost_mcp_simple_calculator --protocol MCP --entrypoint blogpost_mcp_server.py
```

**During configuration, when prompted:**

- Configure OAuth authorizer instead? → **yes**
- Enter OAuth discovery URL: → **Use the Discovery URL from step 1 output**
- Enter allowed OAuth client IDs: → **Use the Machine Client ID from step 1 output**
- Enter allowed OAuth audience: → **Leave empty (press Enter)**

```bash
agentcore launch
```

### 3. Test MCP Server

```bash
python blogpost_local_invoke_remote_mcp_tools.py --name blogpost_mcp_simple_calculator
```

### 4. Update MCP ARN in Agent Script

**Find the MCP ARN in the `.bedrock_agentcore.yaml` file** (created in step 2) and update it in `04_single_agent_mcp/blogpost_single_agent_mcp.py`:

```python
# Update this line in the agent script:
mcp_server_arn = "arn:aws:bedrock-agentcore:eu-central-1:ACCOUNTID:runtime/blogpost_mcp_simple_calculator-{your-id}"
```

### 5. Deploy Agent with MCP Tools

```bash
cd ../04_single_agent_mcp
agentcore configure -e blogpost_single_agent_mcp.py --protocol HTTP -n blogpost_single_agent_mcp
agentcore launch
```

### 6. Test Agent

```bash
agentcore invoke "What is 2+2?"
```

## Required IAM Policy

**Important**: After running `agentcore launch`, you must add this IAM policy to the created execution role:

```json
{
  "Sid": "SSMParameterAccess",
  "Effect": "Allow",
  "Action": ["ssm:GetParameter"],
  "Resource": [
    "arn:aws:ssm:eu-central-1:ACCOUNTID:parameter/app/blogpost/mcp/blogpost_mcp_simple_calculator/machine_client_id",
    "arn:aws:ssm:eu-central-1:ACCOUNTID:parameter/app/blogpost/mcp/blogpost_mcp_simple_calculator/cognito_secret",
    "arn:aws:ssm:eu-central-1:ACCOUNTID:parameter/app/blogpost/mcp/blogpost_mcp_simple_calculator/cognito_discovery_url"
  ]
}
```

**Role Name**: `AmazonBedrockAgentCoreSDKRuntime-eu-central-1-{random-id}`

**Note**: The `{random-id}` is shown in the `agentcore launch` output. Look for lines like:

```
Role name: AmazonBedrockAgentCoreSDKRuntime-eu-central-1-{random-id}
```

## Expected Output

After successful setup, the agent should respond:

```
The sum of 2 + 2 = 4.
```

## Key Differences from User Authentication

- **Setup Script**: Uses `setup_M2M_cognito.py` instead of `setup_cognito.sh`
- **Authentication Type**: Machine-to-Machine (no user interaction required)
- **SSM Parameters**: Stores machine client credentials instead of user credentials
- **Client Type**: Uses machine client for automated authentication
