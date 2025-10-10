#!/bin/bash

# Setup Cognito User Pool for MCP Authentication
# Based on AWS documentation: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html
#
# Usage: ./setup_cognito.sh [mcp_name]
# Example: ./setup_cognito.sh blogpost_mcp_simple_calculator
# If no MCP name provided, defaults to "blogpost_mcp_simple_calculator"

echo "Setting up Cognito User Pool for AgentCore authentication..."

# Check if user pool already exists
echo "Checking if user pool 'BlogpostAgentCoreUserPool' already exists..."
EXISTING_POOL_ID=$(aws cognito-idp list-user-pools \
  --max-results 10 \
  --region eu-central-1 | jq -r '.UserPools[] | select(.Name == "BlogpostAgentCoreUserPool") | .Id')

if [ -n "$EXISTING_POOL_ID" ] && [ "$EXISTING_POOL_ID" != "null" ]; then
  echo "Found existing User Pool: $EXISTING_POOL_ID"
  export POOL_ID="$EXISTING_POOL_ID"
else
  echo "Creating new User Pool..."
  export POOL_ID=$(aws cognito-idp create-user-pool \
    --pool-name "BlogpostAgentCoreUserPool" \
    --policies '{"PasswordPolicy":{"MinimumLength":8}}' \
    --region eu-central-1 | jq -r '.UserPool.Id')
  
  echo "Created User Pool: $POOL_ID"
fi

# Check if app client already exists
echo "Checking if app client 'BlogpostAgentCoreClient' already exists..."
EXISTING_CLIENT_ID=$(aws cognito-idp list-user-pool-clients \
  --user-pool-id $POOL_ID \
  --region eu-central-1 | jq -r '.UserPoolClients[] | select(.ClientName == "BlogpostAgentCoreClient") | .ClientId')

if [ -n "$EXISTING_CLIENT_ID" ] && [ "$EXISTING_CLIENT_ID" != "null" ]; then
  echo "Found existing App Client: $EXISTING_CLIENT_ID"
  export CLIENT_ID="$EXISTING_CLIENT_ID"
else
  echo "Creating new App Client..."
  export CLIENT_ID=$(aws cognito-idp create-user-pool-client \
    --user-pool-id $POOL_ID \
    --client-name "BlogpostAgentCoreClient" \
    --no-generate-secret \
    --explicit-auth-flows "ALLOW_USER_PASSWORD_AUTH" "ALLOW_REFRESH_TOKEN_AUTH" \
    --region eu-central-1 | jq -r '.UserPoolClient.ClientId')
  
  echo "Created App Client: $CLIENT_ID"
fi

# Check if user already exists
echo "Checking if user '***REMOVED***' already exists..."
USER_EXISTS=$(aws cognito-idp admin-get-user \
  --user-pool-id $POOL_ID \
  --username "***REMOVED***" \
  --region eu-central-1 2>/dev/null | jq -r '.Username' 2>/dev/null || echo "null")

if [ "$USER_EXISTS" = "***REMOVED***" ]; then
  echo "User '***REMOVED***' already exists"
else
  echo "Creating user '***REMOVED***'..."
  aws cognito-idp admin-create-user \
    --user-pool-id $POOL_ID \
    --username "***REMOVED***" \
    --temporary-password "***REMOVED***" \
    --region eu-central-1 \
    --message-action SUPPRESS > /dev/null
  
  echo "Created user: ***REMOVED***"
  
  # Set Permanent Password
  aws cognito-idp admin-set-user-password \
    --user-pool-id $POOL_ID \
    --username "***REMOVED***" \
    --password "***REMOVED***" \
    --region eu-central-1 \
    --permanent > /dev/null
  
  echo "Set permanent password"
fi

# Store configuration in SSM Parameter Store
echo "Storing configuration in SSM Parameter Store..."

# Get MCP name from command line or use default
MCP_NAME=${1:-"blogpost_mcp_simple_calculator"}

# Store only the 3 parameters needed for user-based authentication
# Store Client ID
aws ssm put-parameter \
  --name "/app/blogpost/mcp/$MCP_NAME/machine_client_id" \
  --value "$CLIENT_ID" \
  --type "String" \
  --overwrite \
  --description "Cognito Client ID for $MCP_NAME authentication" \
  --region eu-central-1

# Store username and password for user-based auth
aws ssm put-parameter \
  --name "/app/blogpost/mcp/$MCP_NAME/username" \
  --value "***REMOVED***" \
  --type "String" \
  --overwrite \
  --description "Cognito username for $MCP_NAME authentication" \
  --region eu-central-1

aws ssm put-parameter \
  --name "/app/blogpost/mcp/$MCP_NAME/password" \
  --value "***REMOVED***" \
  --type "SecureString" \
  --overwrite \
  --description "Cognito password for $MCP_NAME authentication" \
  --region eu-central-1

echo "Configuration stored in SSM Parameter Store"

# Output the required values
echo ""
echo "Configuration Values:"
echo "Pool ID: $POOL_ID"
echo "Client ID: $CLIENT_ID"
echo "MCP Name: $MCP_NAME"
echo ""
echo "Discovery URL: https://cognito-idp.eu-central-1.amazonaws.com/$POOL_ID/.well-known/openid-configuration"
echo ""
echo "SSM Parameters created (only the 3 needed for user-based authentication):"
echo "- /app/blogpost/mcp/$MCP_NAME/machine_client_id"
echo "- /app/blogpost/mcp/$MCP_NAME/username"
echo "- /app/blogpost/mcp/$MCP_NAME/password"
echo ""
echo "Now you can configure the MCP server with the following command:"
echo "agentcore configure --name $MCP_NAME --protocol MCP --entrypoint blogpost_mcp_server.py"
echo "And then launch the agent with the following command:"
echo "agentcore launch"
