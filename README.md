# Python script to push and pull application config

This script is used to push and pull secrets, s3 config and ssm values for use in applications.

## Usage

### Pushing Config

```
Usage: croudtech-bootstrap put-config [OPTIONS] VALUES_PATH

Options:
  --prefix TEXT   The path prefix (Name prefix used when storing secrets and SSM values)
  --region TEXT   The AWS region (Defaults to the current region set using AWS_DEFAULT_REGION or AWS_REGION env vars)
  --delete-first  Delete the values in this path before pushing (useful for cleanup) This will remove any values with the current path prefix that aren't included in the files we're pushing.
  --help          Show this message and exit.
```

The put-config command requires the following file structure:

```
├── ENVIRONMENT_NAME_1
│   ├── common.yaml
│   ├── common.secret.yaml
│   ├── AppConfig1.yaml
│   ├── AppConfig1.secret.yaml
│   ├── AppConfig2.yaml
│   └── AppConfig2.secret.yaml
├── ENVIRONMENT_NAME_2
│   ├── common.yaml
│   ├── common.secret.yaml
│   ├── AppConfig1.yaml
│   ├── AppConfig1.secret.yaml
│   ├── AppConfig2.yaml
│   └── AppConfig2.secret.yaml
```

Running `python -m croudtech-bootstrap put-config CONFIG_FILES_PATH` will create config for AppConfig1 and AppConfig2 in both defined environments.

common.yaml and common.secret.yaml files contain shared config that will be used for all applications.

### Pulling config

```
Usage: croudtech-bootstrap get-config [OPTIONS]

Options:
  --environment-name TEXT         The environment name  [required]
  --app-name TEXT                 The app name  [required]
  --prefix TEXT                   The path prefix
  --region TEXT                   The AWS region
  --include-common / --ignore-common
                                  Include shared variables
  --output-format [json|yaml|environment|environment-export]
  --parse-redis-param / --ignore-redis-param
                                  Parse redis host and allocate a redis
                                  database number. Requires network access to the redis instance
  --help                          Show this message and exit.
```

Using the put-config example above we can pull the config as follows

```
croudtech-bootstrap get-config --environment-name ENVIRONMENT_NAME_1 --app-name AppConfig1 --output-format environment
```

## Installation

`pip install croudtech-bootstrap`

