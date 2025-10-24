"""
Single Agent with MCP Tools using User-Based Authentication

This script creates a Bedrock AgentCore agent that can use MCP (Model Context Protocol) tools
with user-based Cognito authentication. It retrieves user credentials from SSM Parameter Store
and uses USER_PASSWORD_AUTH flow to get bearer tokens for MCP server authentication.

Prerequisites:
    - Cognito User Pool set up with user credentials stored in SSM
    - MCP server deployed to AgentCore Runtime
    - SSM parameters stored under /app/blogpost/mcp/{mcp_name}/
"""

from strands import Agent
import os
import boto3
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


def get_cognito_bearer_token(mcp_name: str) -> str:
    """
    Get Bearer token from Cognito using user credentials stored in SSM.
    This uses USER_PASSWORD_AUTH flow for user-based authentication.
    """
    try:
        logger.info("Getting Bearer token from Cognito using user credentials...")
        
        # Get stored parameters from SSM
        ssm_client = boto3.client('ssm')
        
        # Get Client ID (user pool client, not machine client)
        client_id = ssm_client.get_parameter(
            Name=f'/app/blogpost/mcp/{mcp_name}/machine_client_id'
        )['Parameter']['Value']
        
        # Get username and password
        username = ssm_client.get_parameter(
            Name=f'/app/blogpost/mcp/{mcp_name}/username'
        )['Parameter']['Value']
        
        password = ssm_client.get_parameter(
            Name=f'/app/blogpost/mcp/{mcp_name}/password',
            WithDecryption=True
        )['Parameter']['Value']
        
        logger.info(f"Retrieved user credentials from SSM")
        logger.info(f"Using username: {username}")
        
        # Use boto3 cognito-idp client directly (no subprocess needed)
        cognito_client = boto3.client('cognito-idp', region_name='eu-central-1')
        
        logger.info(f"Authenticating user with Cognito...")
        
        # Use initiate_auth with USER_PASSWORD_AUTH flow
        response = cognito_client.initiate_auth(
            ClientId=client_id,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': username,
                'PASSWORD': password
            }
        )
        
        # Extract the access token from the response
        access_token = response['AuthenticationResult']['AccessToken']
        
        logger.info(f"Successfully obtained Bearer token using user authentication")
        return access_token
            
    except Exception as e:
        logger.error(f"Error getting Cognito token: {e}")
        raise Exception(f"Error getting Cognito token: {e}")

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
    Create an agent with MCP tools using user-based authentication.
    Following the working example pattern for MCP client connection.
    """
    try:
        global mcp_client
        # MCP server configuration
        mcp_name = "blogpost_mcp_simple_calculator"
        
        # Get MCP server URL - UPDATE THIS WITH YOUR ACTUAL ARN FROM .bedrock_agentcore.yaml
        # Find the ARN in your .bedrock_agentcore.yaml file after running 'agentcore launch'
        mcp_server_arn = "arn:aws:bedrock-agentcore:eu-central-1:ACCOUNTID:runtime/blogpost_mcp_simple_calculator-DEPLOYMENTID"
        region = "eu-central-1"
        encoded_arn = mcp_server_arn.replace(":", "%3A").replace("/", "%2F")
        mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
        
        logger.info(f"MCP Server URL: {mcp_url}")
        logger.info(f"MCP Name: {mcp_name}")
        
        # Get bearer token using user-based authentication
        bearer_token = get_cognito_bearer_token(mcp_name)
        
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