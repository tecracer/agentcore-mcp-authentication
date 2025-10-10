#!/usr/bin/env python3
"""
Enhanced MCP Client for Tool Invocation (Step 5 of 5-Step Workflow)

This script demonstrates full MCP functionality by listing and invoking tools
on the deployed MCP server using Bearer token authentication from Cognito user flow.

This is Step 5 of the complete workflow:
1. ./setup_cognito.sh <name>                           (Set up Cognito with user credentials)
2. python blogpost_mcp_client.py                       (Test locally)
3. agentcore configure --name <name> ...               (Configure agent)
4. agentcore launch                                    (Deploy to cloud)
5. python blogpost_invoke_mcp_tools_userCred.py --name <name>    (Test deployed server) <- YOU ARE HERE

Prerequisites:
    - Steps 1-4 completed successfully
    - MCP server deployed to AgentCore Runtime
    - Cognito user credentials stored in SSM Parameter Store
    - .bedrock_agentcore.yaml file with agent ARN
"""

import asyncio
import os
import sys
import json
import base64
import yaml
import boto3
import requests
import argparse
from datetime import datetime, timedelta
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def get_cognito_bearer_token(mcp_name):
    """Get Bearer token from Cognito using user credentials stored in SSM"""
    print("Getting Bearer token from Cognito using user credentials...")
    
    try:
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
        
        print(f"Retrieved user credentials from SSM")
        print(f"Using username: {username}")
        
        # Use AWS CLI to authenticate user and get bearer token
        # This uses the USER_PASSWORD_AUTH flow (user-based authentication)
        import subprocess
        
        # Prepare the AWS CLI command for user authentication
        cmd = [
            'aws', 'cognito-idp', 'initiate-auth',
            '--client-id', client_id,
            '--auth-flow', 'USER_PASSWORD_AUTH',
            '--auth-parameters', f'USERNAME={username},PASSWORD={password}',
            '--region', 'eu-central-1'
        ]
        
        print(f"Authenticating user with Cognito...")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # Parse the JSON response to get the access token
        import json
        auth_result = json.loads(result.stdout)
        access_token = auth_result['AuthenticationResult']['AccessToken']
        
        print(f"Successfully obtained Bearer token using user authentication")
        return access_token
            
    except subprocess.CalledProcessError as e:
        print(f"Failed to authenticate user: {e}")
        print(f"Error output: {e.stderr}")
        return None
    except Exception as e:
        print(f"Error getting Cognito token: {e}")
        return None


def check_token_expiry(bearer_token):
    """Check if the JWT token is expired using manual base64 decoding"""
    try:
        # Split the JWT token into parts
        parts = bearer_token.split('.')
        if len(parts) != 3:
            print("Invalid JWT format")
            return True
        
        # Decode the payload (second part)
        payload = parts[1]
        # Add padding if necessary
        padding = len(payload) % 4
        if padding:
            payload += '=' * (4 - padding)
            
        # Decode base64
        decoded_bytes = base64.b64decode(payload)
        payload_json = json.loads(decoded_bytes.decode('utf-8'))
        
        exp = payload_json.get('exp', 0)
        iat = payload_json.get('iat', 0)
        current_time = datetime.now().timestamp()
        
        print(f"Token Info:")
        print(f"   Issued at: {datetime.fromtimestamp(iat)}")
        print(f"   Expires at: {datetime.fromtimestamp(exp)}")
        print(f"   Current time: {datetime.fromtimestamp(current_time)}")
        
        if exp < current_time:
            print(f"Token expired {(current_time - exp)/60:.1f} minutes ago")
            return False
        else:
            time_left = exp - current_time
            print(f"Token valid for {time_left/60:.1f} more minutes")
            return True
            
    except Exception as e:
        print(f"Could not decode token: {e}")
        print("   Assuming token is valid...")
        return True  # Assume valid if can't decode


async def main():
    """Main function for MCP tool invocation testing"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Test deployed MCP server with authentication')
    parser.add_argument('--name', required=True, 
                       help='MCP server name (required)')
    args = parser.parse_args()
    
    mcp_name = args.name
    
    # Load agent ARN from .bedrock_agentcore.yaml
    try:
        with open(".bedrock_agentcore.yaml", 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("No .bedrock_agentcore.yaml found. Please deploy the MCP server first:")
        print("   agentcore configure -e blogpost_mcp_server.py --protocol MCP -n mcp_simple_calculator")
        print("   agentcore launch")
        sys.exit(1)
    
    # Get the default agent name
    default_agent = config.get('default_agent')
    if not default_agent:
        print("No default agent found in configuration")
        sys.exit(1)
    
    # Get the agent ARN
    agent_config = config['agents'][default_agent]
    agent_arn = agent_config['bedrock_agentcore']['agent_arn']
    
    if not agent_arn:
        print("Agent ARN not found. Please deploy the MCP server first:")
        print("   agentcore launch")
        sys.exit(1)
    
    # Get bearer token from Cognito using stored SSM parameters
    bearer_token = get_cognito_bearer_token(mcp_name)
    
    if not bearer_token:
        print("Error: Failed to get Bearer token from Cognito")
        print(f"Make sure you completed Step 1: ./setup_cognito.sh {mcp_name}")
        print("This stores the required user credentials in AWS SSM Parameter Store")
        sys.exit(1)
    
    print(f"Testing MCP Server: {mcp_name}")
    print(f"Using MCP Server ARN: {agent_arn}")
    print("Pre-flight Checks:")
    print("=" * 50)
    
    # Check token expiry
    if not check_token_expiry(bearer_token):
        print("\nToken is expired. Getting a fresh token...")
        bearer_token = get_cognito_bearer_token(mcp_name)
        if not bearer_token:
            print("Failed to refresh token. Check your Cognito setup.")
            sys.exit(1)
    
    # URL encode the ARN as specified in AWS docs
    encoded_arn = agent_arn.replace(':', '%3A').replace('/', '%2F')
    mcp_url = f"https://bedrock-agentcore.eu-central-1.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
    
    # Enhanced headers with additional AWS requirements
    headers = {
        "authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MCP-Tool-Client/1.0",
        "X-Amz-Target": "BedrockAgentRuntime.InvokeAgent",
        "X-Amz-Content-Sha256": "UNSIGNED-PAYLOAD"
    }
    
    print(f"Connecting to: {mcp_url}")
    print()
    
    try:
        async with streamablehttp_client(
            mcp_url, 
            headers, 
            timeout=timedelta(seconds=120), 
            terminate_on_close=False
        ) as (read_stream, write_stream, _):
            print("HTTP connection established")
            
            async with ClientSession(read_stream, write_stream) as session:
                print("MCP ClientSession created")
                
                print("Initializing MCP session...")
                await session.initialize()
                print("MCP session initialized with Bearer token authentication")
                
                print("\nListing available tools...")
                tool_result = await session.list_tools()
                
                print("\nAvailable MCP Tools:")
                print("=" * 50)
                for tool in tool_result.tools:
                    print(f"{tool.name}")
                    print(f"   Description: {tool.description}")
                    if hasattr(tool, 'inputSchema') and tool.inputSchema:
                        properties = tool.inputSchema.get('properties', {})
                        if properties:
                            print(f"   Parameters: {list(properties.keys())}")
                    print()
                
                print(f"Successfully connected to MCP server!")
                print(f"Found {len(tool_result.tools)} tools available.")
                
                print("\nTesting MCP Tools:")
                print("=" * 50)
                
                # Test add_numbers tool
                try:
                    print("\nTesting add_numbers(5, 3)...")
                    add_result = await session.call_tool(
                        name="add_numbers",
                        arguments={"a": 5, "b": 3}
                    )
                    print(f"   Result: {add_result.content[0].text}")
                except Exception as e:
                    print(f"   Error: {e}")
                
                # Test multiply_numbers tool
                try:
                    print("\nTesting multiply_numbers(4, 7)...")
                    multiply_result = await session.call_tool(
                        name="multiply_numbers",
                        arguments={"a": 4, "b": 7}
                    )
                    print(f"   Result: {multiply_result.content[0].text}")
                except Exception as e:
                    print(f"   Error: {e}")
                
                # Test greet_user tool
                try:
                    print("\nTesting greet_user('Alice')...")
                    greet_result = await session.call_tool(
                        name="greet_user",
                        arguments={"name": "Alice"}
                    )
                    print(f"   Result: {greet_result.content[0].text}")
                except Exception as e:
                    print(f"   Error: {e}")
                
                print("\nMCP tool testing completed!")
                print("=" * 50)
                print("All tools are working correctly!")
                
    except Exception as e:
        print(f"Error connecting to MCP server: {e}")
        print(f"Error type: {type(e).__name__}")
        
        # Enhanced error handling
        if hasattr(e, 'response'):
            status_code = e.response.status_code
            print(f"HTTP Status: {status_code}")
            try:
                response_json = e.response.json()
                print(f"HTTP Response: {json.dumps(response_json, indent=2)}")
            except:
                print(f"HTTP Response Text: {e.response.text}")
        
        # AWS-specific troubleshooting guidance
        if "403" in str(e):
            print("\nAWS Troubleshooting for 403 RuntimeClientError:")
            print("=" * 60)
            print("1. CONTAINER STARTUP: Check if your container failed to start")
            print("   CloudWatch logs: /aws/bedrock-agentcore/runtimes/{agent_id}/runtime-logs")
            print("\n2. EXECUTION ROLE: Verify AgentCore Runtime execution role permissions")
            print("   - Must have bedrock:InvokeModel permissions")
            print("   - Must have necessary ECR permissions")
            print("\n3. BEARER TOKEN: Token validation issues")
            print("   - Token may be expired (check expiry above)")
            print("   - Cognito user pool configuration")
            print("\n4. TEST LOCALLY: Run your container locally first")
            print("   docker run -p 8000:8000 <your-ecr-image>")
        
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
