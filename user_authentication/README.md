# User-Based Authentication for MCP with Bedrock AgentCore

## Quick Start Commands

### 1. Setup Cognito (User Authentication)

```bash
./setup_cognito.sh blogpost_mcp_simple_calculator
```

### 2. Deploy MCP Server

```bash
agentcore configure --name blogpost_mcp_simple_calculator --protocol MCP --entrypoint blogpost_mcp_server.py
```

**During configuration, when prompted:**

- Configure OAuth authorizer instead? → **yes**
- Enter OAuth discovery URL: → **Use the Discovery URL from step 1 output**
- Enter allowed OAuth client IDs: → **Use the Client ID from step 1 output**
- Enter allowed OAuth audience: → **Leave empty (press Enter)**

```bash
agentcore launch
```

### 3. Test MCP Server

```bash
python blogpost_invoke_mcp_tools_userCred.py --name blogpost_mcp_simple_calculator
```

### 4. Update MCP ARN in Agent Script

**Find the MCP ARN in the `.bedrock_agentcore.yaml` file** (created in step 2) and update it in `blogpost_single_agent_mcp_userCred.py`:

```python
# Update this line in the agent script:
mcp_server_arn = "arn:aws:bedrock-agentcore:eu-central-1:ACCOUNTID:runtime/blogpost_mcp_simple_calculator-{your-id}"
```

### 5. Deploy Agent with MCP Tools

```bash
agentcore configure -e blogpost_single_agent_mcp_userCred.py --protocol HTTP -n blogpost_single_agent_mcp
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
    "arn:aws:ssm:eu-central-1:ACCOUNTID:parameter/app/blogpost/mcp/blogpost_mcp_simple_calculator/username",
    "arn:aws:ssm:eu-central-1:ACCOUNTID:parameter/app/blogpost/mcp/blogpost_mcp_simple_calculator/password"
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
