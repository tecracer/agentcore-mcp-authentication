#!/usr/bin/env python3
"""
Simplified Cognito Setup for Direct MCP Server Access.
Only creates Cognito User Pool and stores required parameters in SSM.
No AgentCore OAuth2 credential provider needed for direct approach.
"""

import boto3
import click
import sys
import random
import string
from botocore.exceptions import ClientError

def get_aws_region():
    """Get AWS region from session."""
    session = boto3.session.Session()
    return session.region_name

def generate_domain_name():
    """Generate a unique domain name for Cognito."""
    # Use a random suffix to avoid conflicts
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"mcp-agent-{suffix}"

def create_cognito_user_pool(mcp_name):
    """Create Cognito User Pool with M2M client for direct MCP access."""
    print("Setting up Cognito User Pool for Direct MCP Access...")
    
    cognito_client = boto3.client('cognito-idp')
    region = get_aws_region()
    
    try:
        # Check if User Pool already exists
        print("Checking for existing User Pool 'BlogpostMCPAgentPool'...")
        existing_pools = cognito_client.list_user_pools(MaxResults=60)
        user_pool_id = None
        
        for pool in existing_pools['UserPools']:
            if pool['Name'] == 'BlogpostMCPAgentPool':
                user_pool_id = pool['Id']
                print(f"Found existing User Pool: {user_pool_id}")
                break
        
        if not user_pool_id:
            # Create User Pool
            print("Creating new User Pool...")
            user_pool_response = cognito_client.create_user_pool(
                PoolName='BlogpostMCPAgentPool',
                MfaConfiguration='OFF',
                UsernameConfiguration={
                    'CaseSensitive': False
                },
                UsernameAttributes=['email'],
                AutoVerifiedAttributes=['email']
            )
            
            user_pool_id = user_pool_response['UserPool']['Id']
            print(f"Created User Pool: {user_pool_id}")
        
        # Check if Resource Server already exists
        print("Checking for existing Resource Server...")
        resource_server_exists = False
        
        try:
            existing_servers = cognito_client.list_resource_servers(
                UserPoolId=user_pool_id,
                MaxResults=50
            )
            
            for server in existing_servers['ResourceServers']:
                if server['Identifier'] == 'blogpost-m2m-resource-server':
                    resource_server_exists = True
                    print(f"Found existing Resource Server: {server['Identifier']}")
                    break
        except ClientError as e:
            # If we can't list resource servers, assume none exist
            pass
        
        if not resource_server_exists:
            # Create Resource Server (required for M2M client)
            print("Creating new Resource Server...")
            resource_server_response = cognito_client.create_resource_server(
                UserPoolId=user_pool_id,
                Identifier='blogpost-m2m-resource-server',
                Name='Blogpost M2M Resource Server',
                Scopes=[
                    {
                        'ScopeName': 'read',
                        'ScopeDescription': 'An example scope created by Amazon Cognito quick start'
                    }
                ]
            )
            
            print("Created Resource Server")
        
        # Handle Cognito Domain - one domain per User Pool (shared across all MCP servers)
        print("Setting up Cognito Domain...")
        domain_name = None
        
        try:
            # Try to create a domain - each User Pool can only have one domain
            temp_domain_name = generate_domain_name()
            cognito_client.create_user_pool_domain(
                Domain=temp_domain_name,
                UserPoolId=user_pool_id
            )
            domain_name = temp_domain_name
            print(f"Created Cognito Domain: {domain_name}")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidParameterException' and 'already has a domain configured' in str(e):
                # Domain already exists for this User Pool - that's fine!
                # All MCP servers will share the same domain
                print("User Pool already has a domain configured (shared across all MCP servers)")
                # Use a predictable pattern based on user pool ID
                pool_suffix = user_pool_id.split('_')[1].lower()
                domain_name = f"mcp-agent-{pool_suffix}"
                print(f"Using existing shared domain: {domain_name}")
            else:
                raise e
        
        # Check if Machine Client already exists for this MCP server
        print("Checking for existing Machine Client...")
        existing_clients = cognito_client.list_user_pool_clients(
            UserPoolId=user_pool_id,
            MaxResults=60
        )
        
        machine_client_id = None
        machine_client_secret = None
        
        # Look for existing client with the same name pattern
        expected_client_name = f'BlogpostMCPAgentMachineClient-{mcp_name}'
        for client in existing_clients['UserPoolClients']:
            if client['ClientName'] == expected_client_name:
                machine_client_id = client['ClientId']
                print(f"Found existing Machine Client: {machine_client_id}")
                break
        
        if not machine_client_id:
            # Create new Machine-to-Machine App Client
            print(f"Creating new Machine Client: {expected_client_name}")
            machine_client_response = cognito_client.create_user_pool_client(
                UserPoolId=user_pool_id,
                ClientName=expected_client_name,
                GenerateSecret=True,
                ExplicitAuthFlows=['ALLOW_REFRESH_TOKEN_AUTH'],
                RefreshTokenValidity=1,
                AccessTokenValidity=60,
                IdTokenValidity=60,
                TokenValidityUnits={
                    'AccessToken': 'minutes',
                    'IdToken': 'minutes',
                    'RefreshToken': 'days'
                },
                AllowedOAuthFlows=['client_credentials'],
                AllowedOAuthScopes=['blogpost-m2m-resource-server/read'],
                AllowedOAuthFlowsUserPoolClient=True,
                SupportedIdentityProviders=['COGNITO'],
                EnableTokenRevocation=True
            )
            
            machine_client_id = machine_client_response['UserPoolClient']['ClientId']
            machine_client_secret = machine_client_response['UserPoolClient']['ClientSecret']
            
            print(f"Created Machine Client: {machine_client_id}")
        else:
            # For existing client, we need to get the secret from SSM or regenerate it
            print("Using existing Machine Client - checking SSM for secret...")
            try:
                ssm_client = boto3.client('ssm')
                machine_client_secret = ssm_client.get_parameter(
                    Name=f'/app/mcp/{mcp_name}/cognito_secret',
                    WithDecryption=True
                )['Parameter']['Value']
                print("Retrieved existing secret from SSM")
            except Exception as e:
                print(f"Could not retrieve secret from SSM: {e}")
                print("You may need to regenerate the client secret manually")
                machine_client_secret = "EXISTING_SECRET_NOT_AVAILABLE"
        
        # Store ALL the parameters needed for direct MCP access
        ssm_client = boto3.client('ssm')
        
        # Store User Pool ID
        ssm_client.put_parameter(
            Name=f'/app/blogpost/mcp/{mcp_name}/userpool_id',
            Value=user_pool_id,
            Type='String',
            Overwrite=True,
            Description=f'Cognito User Pool ID for {mcp_name} MCP server (blogpost)'
        )
        
        # Store Machine Client ID
        ssm_client.put_parameter(
            Name=f'/app/blogpost/mcp/{mcp_name}/machine_client_id',
            Value=machine_client_id,
            Type='String',
            Overwrite=True,
            Description=f'Cognito Machine Client ID for {mcp_name} MCP server (blogpost)'
        )
        
        # Store Machine Client Secret
        ssm_client.put_parameter(
            Name=f'/app/blogpost/mcp/{mcp_name}/cognito_secret',
            Value=machine_client_secret,
            Type='SecureString',
            Overwrite=True,
            Description=f'Cognito Machine Client Secret for {mcp_name} MCP server (blogpost)'
        )
        
        # Store Discovery URL (for OAuth2 discovery)
        discovery_url = f'https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/openid-configuration'
        ssm_client.put_parameter(
            Name=f'/app/blogpost/mcp/{mcp_name}/cognito_discovery_url',
            Value=discovery_url,
            Type='String',
            Overwrite=True,
            Description=f'Cognito Discovery URL for {mcp_name} MCP server (blogpost)'
        )
        
        # Store Cognito Domain (CRITICAL for OAuth2 to work)
        domain_url = f'https://{domain_name}.auth.{region}.amazoncognito.com'
        ssm_client.put_parameter(
            Name=f'/app/blogpost/mcp/{mcp_name}/cognito_domain',
            Value=domain_url,
            Type='String',
            Overwrite=True,
            Description=f'Cognito Domain URL for {mcp_name} OAuth2 token endpoint (blogpost)'
        )
        
        print("Stored required parameters in SSM")
        
        return {
            'user_pool_id': user_pool_id,
            'machine_client_id': machine_client_id,
            'machine_client_secret': machine_client_secret,
            'discovery_url': discovery_url,
            'domain_name': domain_name,
            'domain_url': domain_url
        }
        
    except Exception as e:
        print(f"Failed to create Cognito resources: {e}")
        return None

def delete_cognito_resources(mcp_name):
    """Delete Cognito User Pool and related resources."""
    print(f"Cleaning up Cognito resources for MCP server: {mcp_name}...")
    
    try:
        # Get User Pool ID from SSM
        ssm_client = boto3.client('ssm')
        user_pool_id = ssm_client.get_parameter(
            Name=f'/app/blogpost/mcp/{mcp_name}/userpool_id'
        )['Parameter']['Value']
        
        print(f"Found User Pool: {user_pool_id}")
        
        # Delete Cognito Domain first (if it exists)
        cognito_client = boto3.client('cognito-idp')
        try:
            # Try to delete the domain - we'll use the pattern-based approach
            pool_suffix = user_pool_id.split('_')[1].lower()
            likely_domain_name = f"mcp-agent-{pool_suffix}"
            
            try:
                cognito_client.delete_user_pool_domain(
                    Domain=likely_domain_name,
                    UserPoolId=user_pool_id
                )
                print(f"Deleted Cognito Domain: {likely_domain_name}")
            except ClientError as domain_e:
                if domain_e.response['Error']['Code'] == 'ResourceNotFoundException':
                    print(f"Domain {likely_domain_name} not found (may have been deleted already)")
                else:
                    print(f"Could not delete domain {likely_domain_name}: {domain_e}")
                    
        except Exception as e:
            print(f"Could not delete domain: {e}")
        
        # Delete User Pool (this will cascade delete all related resources)
        cognito_client.delete_user_pool(UserPoolId=user_pool_id)
        
        print(f"Deleted User Pool: {user_pool_id}")
        
        # Delete SSM parameters
        ssm_parameters = [
            f'/app/blogpost/mcp/{mcp_name}/userpool_id',
            f'/app/blogpost/mcp/{mcp_name}/machine_client_id',
            f'/app/blogpost/mcp/{mcp_name}/cognito_secret',
            f'/app/blogpost/mcp/{mcp_name}/cognito_discovery_url',
            f'/app/blogpost/mcp/{mcp_name}/cognito_domain'
        ]
        
        for param_name in ssm_parameters:
            try:
                ssm_client.delete_parameter(Name=param_name)
                print(f"Deleted SSM parameter: {param_name}")
            except ClientError as e:
                if e.response['Error']['Code'] == 'ParameterNotFound':
                    print(f"SSM parameter not found: {param_name}")
                else:
                    print(f"Failed to delete SSM parameter {param_name}: {e}")
        
        print("Cognito resources cleanup complete")
        return True
        
    except Exception as e:
        print(f"Failed to cleanup Cognito resources: {e}")
        return False

@click.group()
@click.pass_context
def cli(ctx):
    """Simplified Cognito Setup for Direct MCP Server Access.
    
    Creates only the Cognito infrastructure needed for direct OAuth2 authentication.
    No AgentCore OAuth2 credential provider needed.
    """
    ctx.ensure_object(dict)

@cli.command()
@click.option('--mcp-name', required=True, help='MCP server name')
def setup(mcp_name):
    """Setup Cognito User Pool for Direct MCP Access."""
    print(f"Setting up Cognito for MCP Server: {mcp_name}")
    print("=" * 60)
    
    # Validate MCP server name
    if not mcp_name.replace('_', '').replace('-', '').isalnum():
        print("MCP server name must contain only letters, numbers, hyphens, and underscores")
        sys.exit(1)
    
    # Create Cognito resources
    cognito_config = create_cognito_user_pool(mcp_name)
    if not cognito_config:
        print("Failed to create Cognito resources")
        sys.exit(1)
    
    print("\nCognito Setup Complete!")
    print(f"User Pool ID: {cognito_config['user_pool_id']}")
    print(f"Machine Client ID: {cognito_config['machine_client_id']}")
    print(f"Cognito Domain: {cognito_config['domain_name']}")
    print(f"Domain URL: {cognito_config['domain_url']}")
    print(f"Discovery URL: {cognito_config['discovery_url']}")
    
    print("\nIMPORTANT - Save These for AgentCore Configuration:")
    print("=" * 60)
    print(f"Discovery URL: {cognito_config['discovery_url']}")
    print(f"Machine Client ID: {cognito_config['machine_client_id']}")
    print("=" * 60)
    print("You'll need these values when running 'agentcore configure'!")
    
    print("\nNext Steps:")
    print("1. Test server locally: python blogpost_mcp_client.py")
    print(f"2. Configure agent: agentcore configure --name {mcp_name} --protocol MCP --entrypoint blogpost_mcp_server.py")
    print("   (Use the Discovery URL and Machine Client ID printed above)")
    print("3. Launch agent: agentcore launch")
    print("4. Test deployed server: python blogpost_invoke_mcp_tools.py")

@cli.command()
@click.option('--mcp-name', required=True, help='MCP server name')
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def cleanup(mcp_name, confirm):
    """Delete Cognito User Pool and related resources."""
    print(f"Cleaning up Cognito resources for MCP server: {mcp_name}...")
    
    # Confirmation prompt
    if not confirm:
        if not click.confirm(f"Are you sure you want to delete all Cognito resources for '{mcp_name}'? This action cannot be undone."):
            click.echo("Operation cancelled")
            sys.exit(0)
    
    # Delete Cognito resources
    if delete_cognito_resources(mcp_name):
        click.echo(f"Cognito resources for '{mcp_name}' deleted successfully")
    else:
        click.echo(f"Failed to delete Cognito resources for '{mcp_name}'", err=True)
        sys.exit(1)

if __name__ == "__main__":
    cli()