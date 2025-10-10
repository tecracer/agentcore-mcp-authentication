The initial issue is, that AGentCore is a quite new service, still in preview and information is sparse.
Nevertheless, some things are present alöready:
Setting up agents is pretty straight forward with the new Starter toolkit of AWS "https://github.com/aws/bedrock-agentcore-starter-toolkit"
The commands agentcore configure, egentcore launch, agentcore invoke (agebntcore monitor and agentcore destroy) make it incredibly easy to create agents. Basic code example (agent.py):

```python
from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands.models import BedrockModel

app = BedrockAgentCoreApp()

@tool
def your_tool(input: str) -> str:
    """Your tool implementation"""
    return "result"

agent = Agent(
    model=BedrockModel(model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0"),
    tools=[your_tool],
    system_prompt="Your system prompt"
)

@app.entrypoint
def strands_agent_bedrock(payload):
    user_input = payload.get("prompt")
    response = agent(user_input)
    return response.message['content'][0]['text']

if __name__ == "__main__":
    app.run()
```

And then agentcore cofigure, etc. read the commands from 01/README.md

I set up my first MCP server (show code of the server, derived from https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html) and according to their Instructions, also using the agentocre confifigure and agentcore deploy commands. Only add --protocol MCP (agentcore configure -e opensearch_mcp_server.py --protocol MCP). Ialso set up a UserPool in Cognito for Athentication (https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html#runtime-mcp-appendix-a), required for deployment, as you have to give these information in the configure step. For testing, I locally connected to the MCP server using a script (and my cognito user) and successfully retrieved the information about the tools. SO far so good, easy!

```python
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

mcp = FastMCP(host="0.0.0.0", stateless_http=True)

@mcp.tool()
def add_numbers(a: int, b: int) -> int:
   """Add two numbers together"""
   return a + b

@mcp.tool()
def multiply_numbers(a: int, b: int) -> int:
   """Multiply two numbers together"""
   return a * b

@mcp.tool()
def greet_user(name: str) -> str:
   """Greet a user by name"""
   return f"Hello, {name}! Nice to meet you."

if __name__ == "__main__":
   mcp.run(transport="streamable-http")
```

Now, let's combine the two pieces into one working system.
I saw about Agent authentication and integration of their AentCore Gateway first time in this video: https://www.youtube.com/watch?v=wzIQDPFQx30
In here, they mask a Lambda behind a AgentCore Gateway to use it similar to a MCP server. My initial thsough was pretty clear: This also has to work with normal MCP servers. Unfortunately, there was no real instruction on how to do that. I took screenshots of their implementation, put it into GenAI and together with this OpenSearch MCP Implementation (https://opensearch.org/blog/hosting-opensearch-mcp-server-with-amazon-bedrock-agentcore/), I finally developed an agent, which should connect to my MCP calculator. Emphasizing: Should. I got this authentication error:
-Paste Error message-

Eventually I found my way into this GitHub Repo (https://github.com/awslabs/amazon-bedrock-agentcore-samples/tree/main/02-use-cases/customer-support-assistant). The actual code of the video I watched around 5 hours ago! At least in a very abstracted and extended way. Crawling through the setups and conficuration files, which were not shown in the Video, I figured, that the used Clpudformation and a custom script to create a specific Cognito User Pool, in which a Machine to Machine client was created.
While the official Documentation of AWS hints, that MCP OAuth authentication happens with Cognito, it was not clear, that their description is for local testing with a specific cognito user, while Agent to MCP communication ahs to happen with a different type of client, the M2M client.

That way, the workflow became pretty obvious:

1. Create a M2M Client in the user Pool and store all required infos in the SSM:
   -Add code bit from the script-

2. Configure your Agent using the correct Discovery ID and Client ID
   -Example from README-
3. Launch the MCP Server

4. Write the Agent (loading the correct SSM parameters and the correct AgentARN)
5. Configure the Agent (no Cognito required, CLI credentials are enough.)
6. Launch the agent
7. Invoke the agent
