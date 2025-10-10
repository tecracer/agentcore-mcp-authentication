from strands import Agent
import os
import boto3
import requests
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from datetime import timedelta
from typing import List, Optional
import traceback
import logging

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_bearer_token(discovery_url: str, client_id: str, client_secret: str) -> str:
    """
    Get OAuth2 bearer token using OAuth2 discovery flow.
    This follows the working example pattern for proper token acquisition.
    """
    try:
        logger.info(f"Fetching OAuth2 discovery data from: {discovery_url}")
        
        # Get discovery data to find token endpoint
        response = requests.get(discovery_url)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch discovery data: {response.status_code}")
            
        discovery_data = response.json()
        token_endpoint = discovery_data['token_endpoint']
        
        logger.info(f"Using token endpoint: {token_endpoint}")
        
        # Client credentials flow
        data = {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        logger.info("Requesting access token...")
        response = requests.post(token_endpoint, data=data, headers=headers)
        
        logger.info(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            token_data = response.json()
            if 'access_token' in token_data:
                logger.info("Access token obtained successfully")
                return token_data['access_token']
            else:
                logger.error(f"No access_token in response: {token_data}")
                raise Exception(f"No access token in response: {token_data}")
        else:
            try:
                error_data = response.json()
                logger.error(f"Token request failed: {error_data}")
            except:
                logger.error(f"Token request failed: {response.text}")
                
            raise Exception(f"Token request failed with status {response.status_code}")
            
    except Exception as e:
        logger.error(f"Error getting bearer token: {str(e)}")
        raise

def get_ssm_parameter(parameter_name: str, decrypt: bool = True) -> str:
    """
    Retrieve a parameter from AWS Systems Manager Parameter Store.
    This follows the Single Responsibility Principle by handling only parameter retrieval.
    """
    try:
        ssm_client = boto3.client('ssm')
        response = ssm_client.get_parameter(
            Name=parameter_name,
            WithDecryption=decrypt
        )
        logger.info(f"SSM parameter {parameter_name} retrieved successfully")
        return response['Parameter']['Value']
    except Exception as e:
        logger.error(f"Failed to retrieve SSM parameter {parameter_name}: {str(e)}")
        raise ValueError(f"Failed to retrieve SSM parameter {parameter_name}: {str(e)}")

app = BedrockAgentCoreApp()
agent = None
mcp_client = None

def create_agent() -> Agent:
    """
    Create an agent with MCP tools using proper OAuth2 discovery flow.
    Following the working example pattern for MCP client connection.
    """
    try:
        global mcp_client
        # Get OAuth2 configuration from SSM
        logger.info("Retrieving OAuth2 configuration...")
        client_id = get_ssm_parameter("/app/blogpost/mcp/blogpost_mcp_simple_calculator/machine_client_id")
        client_secret = get_ssm_parameter("/app/blogpost/mcp/blogpost_mcp_simple_calculator/cognito_secret")
        discovery_url = get_ssm_parameter("/app/blogpost/mcp/blogpost_mcp_simple_calculator/cognito_discovery_url")
        
        # Get MCP server URL - this might need to be adjusted based on your actual deployment
        mcp_server_arn = "arn:aws:bedrock-agentcore:eu-central-1:***REMOVED***:runtime/blogpost_mcp_simple_calculator-OafeR92R9Q"
        region = "eu-central-1"
        encoded_arn = mcp_server_arn.replace(":", "%3A").replace("/", "%2F")
        mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
        
        logger.info(f"MCP Server URL: {mcp_url}")
        logger.info(f"Discovery URL: {discovery_url}")
        
        # Get bearer token using OAuth2 discovery flow (like the working example)
        bearer_token = get_bearer_token(discovery_url, client_id, client_secret)
        
        # Create the MCP client following the working example pattern
        mcp_client = MCPClient(lambda: streamablehttp_client(mcp_url, {
            "authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json"
        }))
        
        # Initialize the model
        model_id = "eu.anthropic.claude-3-7-sonnet-20250219-v1:0"
        model = BedrockModel(model_id=model_id)
        logger.info(f"Using model: {model_id}")
        
        logger.info("Connecting to MCP server to retrieve tools...")
        
        # Start the MCP client (persistent session - following customer support pattern)
        mcp_client.start()
        logger.info("Started persistent MCP client session")
        
        # Get tools without context manager (client stays alive)
        all_tools = mcp_client.list_tools_sync()
        logger.info(f"Retrieved {len(all_tools)} tools from MCP server")
        
        for tool in all_tools:
            # Get tool description from tool_spec dictionary
            tool_desc = tool.tool_spec.get('description', 'No description available')
            logger.info(f"   - {tool.tool_name}: {tool_desc}")
        
        # Create agent with tools (MCP client remains active)
        agent = Agent(
            model=model,
            tools=all_tools,
            system_prompt=f"""You are an intelligent assistant with direct access to MCP (Model Context Protocol) tools.

You have access to the following MCP tools:
{chr(10).join([f"- {tool.tool_name}: {tool.tool_spec.get('description', 'No description available')}" for tool in all_tools])}

Use these tools when appropriate to help users. Always be helpful and accurate in your responses."""
        )
        
        logger.info("Agent created successfully with persistent MCP session!")
        return agent
            
    except Exception as e:
        logger.error(f"Failed to create agent: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise

@app.entrypoint
async def single_agent_mcp_bedrock(payload):
    """
    Invoke the agent with a payload.
    This follows the Single Responsibility Principle by handling only payload processing.
    """
    try:
        global agent

        # Handle both "prompt" and "input" fields for compatibility
        user_input = payload.get("input") or payload.get("prompt")
        if not user_input:
            return "Error: No input provided in payload"
            
        logger.info(f"User input: {user_input}")
        
        # Create agent only once (persistent session)
        if agent is None:
            logger.info("Initializing agent with persistent MCP session...")
            try:
                agent = create_agent()
                logger.info("Agent initialization completed")
            except Exception as e:
                error_msg = f"Failed to create agent: {str(e)}"
                logger.error(error_msg)
                return error_msg
        else:
            logger.info("Using existing agent with persistent MCP session")

        # Run the agent (MCP client already started and persistent)
        logger.info("Running agent...")
        try:
            response = agent(user_input)
            result = response.message['content'][0]['text']
            logger.info(f"Agent response: {result}")
            return result
        except Exception as e:
            error_msg = f"Agent execution failed: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Traceback: {traceback.format_exc()}")
            return error_msg
            
    except Exception as e:
        error_msg = f"Entrypoint failed: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        return error_msg

if __name__ == "__main__":
    app.run()