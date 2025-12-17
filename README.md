# croudtech-bootstrap

A Python CLI tool for managing application configuration across multiple environments using AWS services (S3, SSM Parameter Store, and Secrets Manager).

## Overview

croudtech-bootstrap provides centralized configuration management for applications deployed across multiple environments. It supports:

- **Multi-environment configuration**: Manage separate configurations for production, staging, development, etc.
- **Shared configuration**: Define common values used by all applications in an environment
- **Secret management**: Securely store sensitive values in AWS Secrets Manager
- **Automatic Redis database allocation**: Multi-tenant Redis database management
- **Multiple output formats**: JSON, YAML, shell environment variables

## Installation

```bash
pip install croudtech-bootstrap
```

## Quick Start

### 1. Initialize the bootstrap infrastructure

```bash
croudtech-bootstrap init --environment-name production --region eu-west-2
```

### 2. Create your configuration files

```
config/
├── production/
│   ├── common.yaml           # Shared config for all apps
│   ├── common.secret.yaml    # Shared secrets
│   ├── myapp.yaml            # App-specific config
│   └── myapp.secret.yaml     # App-specific secrets
└── staging/
    ├── common.yaml
    ├── common.secret.yaml
    ├── myapp.yaml
    └── myapp.secret.yaml
```

### 3. Push configuration to AWS

```bash
croudtech-bootstrap put-config ./config
```

### 4. Retrieve configuration

```bash
croudtech-bootstrap get-config --environment-name production --app-name myapp --output-format json
```

## How Values are Stored and Retrieved

### Storage Architecture

Configuration is stored in three AWS services:

| Storage                 | Purpose                  | Path Format                              |
| ----------------------- | ------------------------ | ---------------------------------------- |
| **S3**                  | Raw YAML file backup     | `s3://{bucket}/{environment}/{app}.yaml` |
| **SSM Parameter Store** | Non-sensitive parameters | `/{environment}/{app}/{key}`             |
| **Secrets Manager**     | Sensitive values         | `{environment}/{app}/{key}`              |

### Secret Tagging

When secrets are pushed to AWS Secrets Manager, they are tagged with metadata to enable filtering during retrieval:

| Tag Key       | Tag Value        | Example      |
| ------------- | ---------------- | ------------ |
| `Environment` | Environment name | `production` |
| `App`         | Application name | `myapp`      |

**Why tags matter:** When retrieving secrets, the system queries Secrets Manager using these tags as filters rather than listing all secrets. This ensures:

- Secrets are correctly associated with their app/environment
- Efficient retrieval without scanning all secrets in the account
- Proper isolation between applications and environments

### Retrieval Process

When you retrieve configuration using `get-config`:

1. **Fetch app-specific values** from S3 (`{environment}/{app}.yaml`)
2. **Fetch app-specific secrets** from Secrets Manager (tagged with `Environment` and `App`)
3. **If `--include-common` is enabled** (default), fetch common values and secrets
4. **Merge configurations**: App-specific values override common values
5. **Flatten nested structures**: Convert nested YAML to flat key-value pairs
6. **Process special values**: Auto-allocate Redis databases if configured

### Value Flattening

Nested YAML structures are automatically flattened using underscore separators:

```yaml
# Input (myapp.yaml)
database:
  host: localhost
  port: 5432
  credentials:
    username: admin

# Output (flattened)
database_host: localhost
database_port: 5432
database_credentials_username: admin
```

### Configuration Merging

Common configuration is merged with app-specific configuration, with app values taking precedence:

```yaml
# common.yaml
LOG_LEVEL: INFO
DATABASE_HOST: shared-db.example.com

# myapp.yaml
LOG_LEVEL: DEBUG  # Overrides common
API_KEY: abc123

# Result
LOG_LEVEL: DEBUG        # From myapp.yaml (overrides common)
DATABASE_HOST: shared-db.example.com  # From common.yaml
API_KEY: abc123         # From myapp.yaml
```

## Configuration File Structure

### Directory Layout

```
VALUES_PATH/
├── ENVIRONMENT_1/
│   ├── common.yaml           # Shared config (all apps inherit)
│   ├── common.secret.yaml    # Shared secrets (all apps inherit)
│   ├── app1.yaml             # App1 configuration
│   ├── app1.secret.yaml      # App1 secrets
│   ├── app2.yaml             # App2 configuration
│   └── app2.secret.yaml      # App2 secrets
├── ENVIRONMENT_2/
│   ├── common.yaml
│   ├── common.secret.yaml
│   ├── app1.yaml
│   └── app1.secret.yaml
```

### File Naming Conventions

| File Pattern         | Purpose                     | Storage Location         |
| -------------------- | --------------------------- | ------------------------ |
| `{app}.yaml`         | Non-sensitive configuration | S3 + SSM Parameter Store |
| `{app}.secret.yaml`  | Sensitive configuration     | Secrets Manager          |
| `common.yaml`        | Shared non-sensitive config | Merged with all apps     |
| `common.secret.yaml` | Shared secrets              | Merged with all apps     |

### Example Configuration Files

**production/common.yaml** - Shared environment settings:

```yaml
AWS_REGION: eu-west-2
LOG_LEVEL: INFO
REDIS_HOST: redis.example.com
REDIS_PORT: 6379
REDIS_DB: auto # Auto-allocate database number
```

**production/myapp.yaml** - Application-specific settings:

```yaml
APP_NAME: myapp
API_VERSION: v2
database:
  host: db.example.com
  port: 5432
  name: myapp_production
```

**production/myapp.secret.yaml** - Sensitive values:

```yaml
database:
  password: supersecretpassword
API_SECRET_KEY: abc123xyz
```

## CLI Commands

### Global Options

```bash
croudtech-bootstrap [OPTIONS] COMMAND

Options:
  --endpoint-url TEXT  AWS API endpoint URL (for testing with LocalStack)
  --put-metrics       Enable CloudWatch metrics tracking (default: True)
  --bucket-name TEXT  S3 bucket name (default: app-bootstrap-{AWS_ACCOUNT_ID})
```

### init

Initialize bootstrap infrastructure by creating the S3 bucket.

```bash
croudtech-bootstrap init --environment-name ENVIRONMENT --region REGION
```

### put-config

Push local configuration files to AWS.

```bash
croudtech-bootstrap put-config [OPTIONS] VALUES_PATH

Options:
  --prefix TEXT      SSM parameter path prefix (default: /appconfig)
  --region TEXT      AWS region (default: eu-west-2)
  --delete-first     Remove orphaned parameters/secrets before pushing
```

**Example:**

```bash
croudtech-bootstrap put-config ./config --region eu-west-2 --delete-first
```

### get-config

Retrieve configuration for a specific application and environment.

```bash
croudtech-bootstrap get-config [OPTIONS]

Options:
  --environment-name TEXT    Environment name (required)
  --app-name TEXT           Application name (required)
  --prefix TEXT             SSM path prefix (default: /appconfig)
  --region TEXT             AWS region (default: eu-west-2)
  --include-common/--ignore-common
                            Include shared config (default: include)
  --output-format [json|yaml|environment|environment-export]
                            Output format (default: json)
  --parse-redis-param/--ignore-redis-param
                            Auto-allocate Redis DB (default: parse)
```

**Output Format Examples:**

```bash
# JSON output (default)
croudtech-bootstrap get-config --environment-name production --app-name myapp

# YAML output
croudtech-bootstrap get-config --environment-name production --app-name myapp --output-format yaml

# Shell variables (for sourcing)
croudtech-bootstrap get-config --environment-name production --app-name myapp --output-format environment
# Output: DATABASE_HOST="db.example.com"

# Shell exports (for subshells)
croudtech-bootstrap get-config --environment-name production --app-name myapp --output-format environment-export
# Output: export DATABASE_HOST="db.example.com"
```

### list-apps

List all applications stored in S3 across all environments.

```bash
croudtech-bootstrap list-apps --region eu-west-2
```

### cleanup-secrets

Remove orphaned secrets from AWS Secrets Manager.

```bash
croudtech-bootstrap cleanup-secrets VALUES_PATH --region eu-west-2
```

### manage-redis

Redis database allocation management commands.

```bash
# Show allocated database for an app
croudtech-bootstrap manage-redis show-db \
  --environment-name production \
  --app-name myapp

# Show all database allocations
croudtech-bootstrap manage-redis show-dbs \
  --redis-host redis.example.com \
  --redis-port 6379

# Manually allocate a database
croudtech-bootstrap manage-redis allocate-db \
  --redis-host redis.example.com \
  --redis-port 6379 \
  --environment-name production \
  --app-name myapp

# Remove a database allocation
croudtech-bootstrap manage-redis deallocate-db \
  --redis-host redis.example.com \
  --redis-port 6379 \
  --environment-name production \
  --app-name myapp
```

## Redis Database Auto-Allocation

When multiple applications share a single Redis instance, croudtech-bootstrap can automatically allocate unique database numbers to each application.

### How It Works

1. **Database 15** is reserved for storing allocation metadata
2. **Databases 0-14** are available for applications
3. Allocations are tracked using keys in format `{environment}_{app_name}`
4. When `REDIS_DB=auto` is configured, a database is automatically allocated

### Configuration

In your `common.yaml` or `{app}.yaml`:

```yaml
REDIS_HOST: redis.example.com
REDIS_PORT: 6379
REDIS_DB: auto # Triggers auto-allocation
```

### Output

When configuration is retrieved with Redis auto-allocation:

```json
{
  "REDIS_HOST": "redis.example.com",
  "REDIS_PORT": 6379,
  "REDIS_DB": 3,
  "REDIS_URL": "redis://redis.example.com:6379/3"
}
```

## Programmatic Usage

You can use croudtech-bootstrap programmatically in your Python applications:

```python
from croudtech_bootstrap_app.bootstrap import BootstrapParameters

# Initialize the parameters retriever
params = BootstrapParameters(
    environment_name="production",
    app_name="myapp",
    bucket_name="app-bootstrap-123456789",
    region="eu-west-2",
    include_common=True,
    parse_redis=True,
)

# Get flattened parameters
config = params.get_params()
print(config["DATABASE_HOST"])
print(config["REDIS_URL"])

# Get parameters preserving nested structure
raw_config = params.get_raw_params()
print(raw_config["database"]["host"])

# Export as environment variables
env_string = params.params_to_env(export=True)
# Returns: export DATABASE_HOST="db.example.com"\nexport API_KEY="..."
```

## AWS Permissions

The following IAM permissions are required:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket",
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::app-bootstrap-*",
        "arn:aws:s3:::app-bootstrap-*/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "ssm:PutParameter",
        "ssm:DeleteParameter",
        "ssm:DescribeParameters",
        "ssm:GetParameter",
        "ssm:AddTagsToResource"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:CreateSecret",
        "secretsmanager:UpdateSecret",
        "secretsmanager:DeleteSecret",
        "secretsmanager:GetSecretValue",
        "secretsmanager:ListSecrets"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["cloudwatch:PutMetricData"],
      "Resource": "*"
    }
  ]
}
```

## Environment Variables

| Variable                             | Description                                  | Default     |
| ------------------------------------ | -------------------------------------------- | ----------- |
| `AWS_DEFAULT_REGION` or `AWS_REGION` | AWS region                                   | `eu-west-2` |
| `AWS_ENDPOINT_URL`                   | Custom AWS endpoint (for LocalStack testing) | None        |
| `LOG_LEVEL`                          | Logging verbosity                            | `INFO`      |

## Testing with LocalStack

For local development and testing:

```bash
# Start LocalStack
docker-compose up -d localstack

# Use croudtech-bootstrap with LocalStack
croudtech-bootstrap --endpoint-url http://localhost:4566 init --environment-name test
croudtech-bootstrap --endpoint-url http://localhost:4566 put-config ./config
```

## Troubleshooting

### Common Issues

**"Parameter value is too large to store"**

- SSM Parameter Store has a 4096 byte limit for standard parameters
- Consider using Secrets Manager for larger values or splitting configuration

**"Couldn't allocate Redis Database"**

- Ensure REDIS_HOST is correctly configured
- Check that the Redis instance is accessible
- Verify databases 0-14 aren't all allocated

**"Bucket already exists but is not owned by you"**

- The default bucket name uses your AWS account ID
- Specify a custom bucket name with `--bucket-name`

## License

MIT License
