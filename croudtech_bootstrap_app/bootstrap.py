from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import botocore.exceptions

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
    from mypy_boto3_secretsmanager import SecretsManagerClient
    from mypy_boto3_ssm import SSMClient
else:
    S3Client = object
    SSMClient = object

import json
import logging
import os
import re
import shutil
import tempfile
import time
import typing
from collections.abc import MutableMapping

import boto3
import botocore
import click
import yaml

from croudtech_bootstrap_app.logging import init as initLogs

from .redis_config import RedisConfig

logger = initLogs()


AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL", None)


class Utils:
    """Utility functions for the bootstrap application."""

    @staticmethod
    def chunk_list(data, chunk_size):
        """
        Split a list into chunks of a specified size.

        Args:
            data: The list to split.
            chunk_size: The maximum size of each chunk.

        Yields:
            List chunks of the specified size.
        """
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]


class BootstrapParameters:
    """
    High-level interface for retrieving application configuration parameters.

    This class provides a simplified API for fetching configuration values and secrets
    for a specific application and environment combination. It handles merging common
    configuration with app-specific configuration and supports automatic Redis database
    allocation.

    Value Storage and Retrieval:
        Configuration is stored in AWS using a hierarchical structure:
        - S3: Raw YAML files stored at s3://{bucket}/{environment}/{app}.yaml
        - Secrets Manager: Sensitive values stored at {environment}/{app}/{key}
        - SSM Parameter Store: Non-sensitive values (used during push)

        When retrieving parameters:
        1. App-specific values are fetched from S3
        2. If include_common=True, common values are also fetched
        3. Values are merged (app-specific overrides common)
        4. Nested YAML is flattened using underscore separators
           e.g., {db: {host: "localhost"}} becomes {"db_host": "localhost"}
        5. If parse_redis=True and REDIS_DB=auto, a Redis DB is allocated

    Example:
        >>> params = BootstrapParameters(
        ...     environment_name="production",
        ...     app_name="myapp",
        ...     bucket_name="app-bootstrap-123456789"
        ... )
        >>> config = params.get_params()
        >>> print(config["DATABASE_URL"])

    Args:
        environment_name: The target environment (e.g., "production", "staging").
        app_name: The application name (must match the YAML filename without extension).
        bucket_name: S3 bucket name where configuration is stored.
        click: Click module for CLI output (default: click module).
        prefix: SSM parameter path prefix (default: "/appconfig").
        region: AWS region (default: "eu-west-2").
        include_common: Whether to merge common.yaml values (default: True).
        use_sns: Whether to use SNS notifications (default: True).
        endpoint_url: Custom AWS endpoint URL for testing (default: from env).
        parse_redis: Whether to auto-allocate Redis databases (default: True).
    """

    def __init__(
        self,
        environment_name,
        app_name,
        bucket_name,
        click=click,
        prefix="/appconfig",
        region="eu-west-2",
        include_common=True,
        use_sns=True,
        endpoint_url=AWS_ENDPOINT_URL,
        parse_redis=True,
    ):
        self.environment_name = environment_name
        self.app_name = app_name
        self.bucket_name = bucket_name
        self.click = click
        self.prefix = prefix
        self.region = region
        self.include_common = include_common
        self.logger = logging.getLogger(self.__class__.__name__)
        self.use_sns = use_sns
        self.endpoint_url = endpoint_url
        self.put_metrics = False
        self.parse_redis = parse_redis

    @property
    def bootstrap_manager(self) -> BootstrapManager:
        """Lazily instantiated BootstrapManager for AWS operations."""
        if not hasattr(self, "_bootstrap_manager"):
            self._bootstrap_manager = BootstrapManager(
                prefix=self.prefix,
                region=self.region,
                click=self.click,
                values_path=None,
                bucket_name=self.bucket_name,
                endpoint_url=self.endpoint_url,
            )
        return self._bootstrap_manager

    @property
    def environment(self) -> BootstrapEnvironment:
        """Lazily instantiated BootstrapEnvironment for the target environment."""
        if not hasattr(self, "_environment"):
            self._environment = BootstrapEnvironment(
                name=self.environment_name, path=None, manager=self.bootstrap_manager
            )
        return self._environment

    @property
    def app(self) -> BootstrapApp:
        """Lazily instantiated BootstrapApp for the target application."""
        if not hasattr(self, "_app"):
            self._app = BootstrapApp(
                name=self.app_name, path=None, environment=self.environment
            )
        return self._app

    @property
    def common_app(self) -> BootstrapApp:
        """Lazily instantiated BootstrapApp for retrieving common configuration."""
        if not hasattr(self, "_common_app"):
            self._common_app = BootstrapApp(
                name="common", path=None, environment=self.environment
            )
        return self._common_app

    def get_redis_db(self):
        """
        Get the allocated Redis database number for this application.

        Returns:
            tuple: (redis_db, redis_host, redis_port) or (None, None, None) if not configured.
        """
        parameters = self.get_params()
        redis_db, redis_host, redis_port = self.find_redis_config(parameters)
        return redis_db, redis_host, redis_port

    def find_redis_config(self, parameters, allocate=False):
        """
        Extract Redis configuration from parameters and optionally allocate a database.

        If REDIS_DB is not set or is set to "auto", this method will look up or allocate
        a Redis database number from the shared Redis allocation system.

        Args:
            parameters: Dictionary of configuration parameters.
            allocate: If True, allocate a new database if one doesn't exist.

        Returns:
            tuple: (redis_db, redis_host, redis_port) or (None, None, None) if not configured.
        """
        if "REDIS_DB" not in parameters or parameters["REDIS_DB"] == "auto":
            redis_host = (
                parameters["REDIS_HOST"] if "REDIS_HOST" in parameters else False
            )
            redis_port = (
                parameters["REDIS_PORT"] if "REDIS_PORT" in parameters else 6379
            )

            if redis_host is not None:
                redis_config_instance = RedisConfig(
                    redis_host=redis_host,
                    redis_port=redis_port,
                    app_name=self.app_name,
                    environment=self.environment_name,
                    put_metrics=self.put_metrics,
                )
                redis_db = redis_config_instance.get_redis_database(allocate)
                return redis_db, redis_host, redis_port
        return None, None, None

    def parse_params(self, parameters):
        """
        Post-process parameters to handle special values like Redis auto-allocation.

        If parse_redis is enabled and REDIS_HOST is configured, this will allocate
        a Redis database and generate a REDIS_URL.

        Args:
            parameters: Dictionary of configuration parameters.

        Returns:
            dict: Parameters with REDIS_DB and REDIS_URL populated if applicable.

        Raises:
            Exception: If Redis auto-allocation is required but fails.
        """
        if self.parse_redis:
            redis_db, redis_host, redis_port = self.find_redis_config(
                parameters, allocate=True
            )
            if redis_db or redis_db == 0:
                parameters["REDIS_DB"] = redis_db
                parameters["REDIS_URL"] = "redis://%s:%s/%s" % (
                    redis_host,
                    redis_port,
                    redis_db,
                )
            else:
                raise Exception("Couldn't allocate Redis Database")
        return parameters

    def get_params(self):
        """
        Retrieve flattened configuration parameters for the application.

        Fetches configuration from S3, merges common config if enabled,
        flattens nested structures, and processes special values.

        Returns:
            dict: Flattened key-value pairs of configuration parameters.
        """
        app_params = self.app.get_remote_params()

        if self.include_common:
            common_params = self.common_app.get_remote_params()
            app_params = {**common_params, **app_params}
        return self.parse_params(app_params)

    def get_raw_params(self):
        """
        Retrieve configuration parameters preserving nested structure.

        Similar to get_params() but keeps the original YAML nesting structure
        instead of flattening to underscore-separated keys.

        Returns:
            dict: Configuration parameters with original nested structure.
        """
        app_params = self.app.get_remote_params(flatten=False)

        if self.include_common:
            common_params = self.common_app.get_remote_params(flatten=False)
            app_params = {**common_params, **app_params}
        return self.parse_params(app_params)

    def params_to_env(self, export=False):
        """
        Convert configuration parameters to shell environment variable format.

        Generates shell-compatible variable assignments that can be sourced
        or exported. Special characters in values are escaped.

        Args:
            export: If True, prefix each line with "export " for subshell use.

        Returns:
            str: Newline-separated environment variable assignments.

        Example:
            >>> params.params_to_env()
            'DATABASE_URL="postgres://..."\\nAPI_KEY="secret"'
            >>> params.params_to_env(export=True)
            'export DATABASE_URL="postgres://..."\\nexport API_KEY="secret"'
        """
        strings = []
        for parameter, value in self.get_params().items():
            os.environ[parameter] = str(value)
            prefix = "export " if export else ""
            strings.append(
                '%s%s="%s"'
                % (
                    prefix,
                    parameter,
                    str(value).replace("\n", "\\n").replace('"', '\\"'),
                )
            )
            logger.debug("Imported %s from SSM to env var %s" % (parameter, parameter))

        return "\n".join(strings)


class BootstrapApp:
    """
    Represents a single application's configuration within an environment.

    This class manages both local (YAML files) and remote (AWS) configuration
    for an application. It handles reading local configuration files, fetching
    remote values from S3 and Secrets Manager, and pushing configuration to AWS.

    Configuration File Naming Convention:
        - {app_name}.yaml: Non-sensitive configuration values
        - {app_name}.secret.yaml: Sensitive values (stored in Secrets Manager)

    Storage Locations:
        - S3: s3://{bucket}/{environment}/{app_name}.yaml
        - Secrets Manager: {environment}/{app_name}/{secret_key}
        - SSM Parameter Store: /{environment}/{app_name}/{parameter_key}

    Value Flattening:
        Nested YAML structures are flattened using underscore separators:
        ```yaml
        database:
          host: localhost
          port: 5432
        ```
        Becomes: {"database_host": "localhost", "database_port": "5432"}

    Args:
        name: The application name (matches filename without .yaml extension).
        path: Local filesystem path to the app's YAML configuration file.
        environment: Parent BootstrapEnvironment instance.

    Example:
        >>> app = BootstrapApp("myapp", "/config/prod/myapp.yaml", environment)
        >>> local_config = app.local_values
        >>> remote_config = app.remote_values
    """

    environment: BootstrapEnvironment

    def __init__(self, name, path, environment: BootstrapEnvironment):
        self.name = name
        self.path = path
        self.environment = environment

    @property
    def s3_client(self) -> S3Client:
        """AWS S3 client from parent manager."""
        return self.environment.manager.s3_client

    @property
    def ssm_client(self) -> SSMClient:
        """AWS SSM client from parent manager."""
        return self.environment.manager.ssm_client

    @property
    def secrets_client(self) -> SecretsManagerClient:
        """AWS Secrets Manager client from parent manager."""
        return self.environment.manager.secrets_client

    @property
    def secret_path(self):
        """Local filesystem path to the app's secret YAML file."""
        return os.path.join(self.environment.path, f"{self.name}.secret.yaml")

    def upload_to_s3(self):
        """Upload the local YAML configuration file to S3."""
        source = self.path
        bucket = self.environment.manager.bucket_name
        dest = os.path.join("", self.environment.name, os.path.basename(self.path))

        self.environment.manager.click.secho(
            f"Uploading {source} to s3://{bucket}/{dest}"
        )

        self.s3_client.upload_file(source, bucket, dest)

        self.environment.manager.click.secho(
            f"Uploaded {source} to s3://{bucket}/{dest}"
        )

    @property
    def s3_key(self):
        """S3 object key for this app's configuration: {environment}/{app}.yaml"""
        return os.path.join("", self.environment.name, ".".join([self.name, "yaml"]))

    def fetch_from_s3(self, raw=False) -> typing.Dict[str, Any]:
        """
        Fetch configuration values from S3.

        Args:
            raw: If True, return values without JSON parsing.

        Returns:
            dict: Configuration values from the S3-stored YAML file.
        """
        if not hasattr(self, "_s3_data"):
            response = self.s3_client.get_object(
                Bucket=self.environment.manager.bucket_name, Key=self.s3_key
            )
            self._s3_data = yaml.load(response["Body"], Loader=yaml.SafeLoader)
            if raw:
                return self._s3_data
            for key, value in self._s3_data.items():
                self._s3_data[key] = self.parse_value(value)

        return self._s3_data

    def parse_value(self, value):
        """
        Parse a configuration value, detecting and handling JSON strings.

        Args:
            value: The raw value to parse.

        Returns:
            str: The parsed value as a string, with JSON properly serialized.
        """
        try:
            parsed_value = json.dumps(json.loads(value))
        except json.decoder.JSONDecodeError:
            parsed_value = value
        except TypeError:
            parsed_value = value
        return str(parsed_value).strip()

    def cleanup_ssm_parameters(self):
        """
        Remove SSM parameters that exist remotely but not in local configuration.

        Compares local YAML keys with remote SSM parameters and deletes
        any remote parameters that no longer have corresponding local definitions.
        """
        local_value_keys = set(self.convert_flatten(self.local_values).keys() or [])
        self.raw = True
        remote_value_keys = set(self.remote_values or [])
        self.raw = None

        orphaned_ssm_parameters = remote_value_keys - local_value_keys

        for parameter in orphaned_ssm_parameters:
            parameter_id = self.get_parameter_id(parameter)
            try:
                self.ssm_client.delete_parameter(Name=self.get_parameter_id(parameter))
                logger.info(f"Deleted orphaned ssm parameter {parameter}")
            except Exception:
                logger.info(f"Parameter: {parameter_id} could not be deleted")

    def cleanup_secrets(self):
        """
        Remove secrets from AWS Secrets Manager that no longer exist locally.

        Compares local secret YAML keys with remote secrets and permanently
        deletes any remote secrets without corresponding local definitions.
        """
        local_secret_keys = self.convert_flatten(self.local_secrets).keys()
        remote_secret_keys = self.remote_secret_records.keys()

        orphaned_secrets = [
            item
            for item in remote_secret_keys
            if re.sub(r"(-[a-zA-Z]{6})$", "", item) not in local_secret_keys
        ]

        for secret in orphaned_secrets:
            secret_record = self.remote_secrets[secret]
            self.secrets_client.delete_secret(
                SecretId=secret_record["ARN"], ForceDeleteWithoutRecovery=True
            )
            logger.info(f"Deleted orphaned secret {secret_record['ARN']}")

    @property
    def local_secrets(self) -> typing.Dict[str, Any]:
        """
        Local secrets loaded from {app_name}.secret.yaml file.

        Returns:
            dict: Secret key-value pairs, or empty dict if file doesn't exist.
        """
        if not hasattr(self, "_secrets"):
            self._secrets = {}
            if os.path.exists(self.secret_path):
                with open(self.secret_path) as file:
                    secrets = yaml.safe_load(file)
                if secrets:
                    self._secrets = secrets

        return self._secrets

    @property
    def local_values(self) -> typing.Dict[str, Any]:
        """
        Local configuration values loaded from {app_name}.yaml file.

        Returns:
            dict: Configuration key-value pairs, or empty dict if file doesn't exist.
        """
        if not hasattr(self, "_values"):
            self._values = {}
            if os.path.exists(self.path):
                with open(self.path) as file:
                    values = yaml.safe_load(file)
                if values:
                    self._values = values

        return self._values

    @property
    def remote_secrets(self) -> typing.Dict[str, Any]:
        """
        Remote secrets fetched from AWS Secrets Manager.

        Returns:
            dict: Secret key-value pairs from Secrets Manager.
        """
        if not hasattr(self, "_remote_secrets"):
            self._remote_secrets = self.get_remote_secrets()

        return self._remote_secrets

    @property
    def remote_secret_records(self) -> typing.Dict[str, Any]:
        """
        Remote secret metadata records from AWS Secrets Manager.

        Returns:
            dict: Secret metadata keyed by secret name.
        """
        if not hasattr(self, "_remote_secrets"):
            self._remote_secrets = self.get_remote_secret_records()

        return self._remote_secrets

    @property
    def remote_ssm_parameters(self) -> typing.Dict[str, Any]:
        """
        Remote parameters fetched from AWS SSM Parameter Store.

        Returns:
            dict: Parameter metadata keyed by parameter name.
        """
        if not hasattr(self, "_remote_parameters"):
            self._remote_parameters = self.get_remote_ssm_parameters()

        return self._remote_parameters

    @property
    def remote_values(self) -> typing.Dict[str, Any]:
        """
        Remote configuration values fetched from S3.

        Returns:
            dict: Configuration key-value pairs from S3, or empty dict on error.
        """
        if not hasattr(self, "_remote_values"):
            try:
                self._remote_values = self.fetch_from_s3(self.raw)
            except botocore.exceptions.ClientError as err:
                self.environment.manager.click.secho(err)
                self._remote_values = {}

        return self._remote_values

    def get_local_params(self):
        """
        Get merged local values and secrets, flattened.

        Returns:
            dict: Combined and flattened local configuration.
        """
        app_values = self.convert_flatten(self.local_values)
        app_secrets = self.convert_flatten(self.local_secrets)
        return {**app_values, **app_secrets}

    def get_remote_params(self, flatten=True):
        """
        Get merged remote values and secrets from AWS.

        Args:
            flatten: If True, flatten nested structures using underscore separators.

        Returns:
            dict: Combined remote configuration (values + secrets).
        """
        if flatten:
            self.raw = False
            app_values = self.convert_flatten(self.remote_values)
            app_secrets = self.convert_flatten(self.remote_secrets)
        else:
            self.raw = True
            app_values = self.remote_values
            app_secrets = self.remote_secrets
        return {**app_values, **app_secrets}

    def get_flattened_parameters(self) -> typing.Dict[str, Any]:
        """Get local values with nested structures flattened."""
        return self.convert_flatten(self.local_values)

    def get_flattened_secrets(self) -> typing.Dict[str, Any]:
        """Get local secrets with nested structures flattened."""
        return self.convert_flatten(self.local_secrets)

    def get_parameter_id(self, parameter):
        """Generate SSM parameter path: /{environment}/{app}/{parameter}"""
        return f"/{self.get_secret_id(parameter)}"

    def get_secret_id(self, secret):
        """Generate secret path: {environment}/{app}/{secret}"""
        return os.path.join("", self.environment.name, self.name, secret)

    def put_parameter(
        self, parameter_id, parameter_value, tags=None, type="String", overwrite=True
    ):
        """
        Create or update an SSM parameter.

        Args:
            parameter_id: Full parameter path (e.g., /{env}/{app}/{key}).
            parameter_value: The value to store.
            tags: Optional list of tag dicts with Key and Value.
            type: SSM parameter type (default: "String").
            overwrite: Whether to overwrite existing values (default: True).
        """
        print(f"Creating Parameter {parameter_id}")
        self.ssm_client.put_parameter(
            Name=parameter_id,
            Value=parameter_value,
            Type=type,
            Overwrite=overwrite,
        )
        if tags:
            self.ssm_client.add_tags_to_resource(
                ResourceType="Parameter", ResourceId=parameter_id, Tags=tags
            )

    def create_secret(self, Name, SecretString, Tags, ForceOverwriteReplicaSecret):
        """
        Create or update a secret in AWS Secrets Manager.

        Automatically handles the case where the secret already exists
        by updating it instead.

        Args:
            Name: Secret name/path (e.g., {env}/{app}/{key}).
            SecretString: The secret value to store.
            Tags: List of tag dicts (ignored, tags are auto-generated).
            ForceOverwriteReplicaSecret: Whether to force overwrite replicas.
        """
        print(f"Creating Secret {Name}")
        try:
            self.secrets_client.create_secret(
                Name=Name,
                SecretString=SecretString,
                Tags=[
                    {"Key": "Environment", "Value": self.environment.name},
                    {"Key": "App", "Value": self.name},
                ],
                ForceOverwriteReplicaSecret=True,
            )
        except self.secrets_client.exceptions.ResourceExistsException:
            self.secrets_client.update_secret(
                SecretId=Name,
                SecretString=SecretString,
            )

    def backoff_with_custom_exception(
        self,
        func,
        exception,
        message_prefix="",
        max_attempts=5,
        base_delay=1,
        max_delay=10,
        factor=2,
        *args,
        **kwargs,
    ):
        """
        Execute a function with exponential backoff retry on specified exceptions.

        Args:
            func: The function to execute.
            exception: The exception type to catch and retry on.
            message_prefix: Prefix for log messages.
            max_attempts: Maximum number of retry attempts (default: 5).
            base_delay: Initial delay in seconds (default: 1).
            max_delay: Maximum delay in seconds (default: 10).
            factor: Exponential backoff factor (default: 2).
            *args, **kwargs: Arguments to pass to the function.

        Returns:
            The result of the function if successful.

        Raises:
            The caught exception if all attempts fail.
        """
        attempts = 0
        delay = base_delay

        while attempts < max_attempts:
            try:
                result = func(*args, **kwargs)
                return result  # Return result if successful
            except exception as e:
                print(f"{message_prefix} Attempt {attempts+1} failed: {e}")
                attempts += 1
                if attempts == max_attempts:
                    raise  # If all attempts fail, raise the last exception

                # Backoff logic
                delay = min(delay * factor, max_delay)
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)

    def push_parameters(self):
        """
        Push all local parameters to AWS SSM Parameter Store.

        Iterates through flattened local values and creates/updates
        corresponding SSM parameters. Skips values larger than 4096 bytes
        (SSM limit) or empty values.
        """
        for parameter, value in self.get_flattened_parameters().items():
            parameter_value = str(value)
            if (
                value_size := sys.getsizeof(parameter_value)
            ) > 4096 or not parameter_value:
                self.environment.manager.click.secho(
                    f"Parameter: {parameter} value is too large to store ({value_size})"
                )
                continue
            parameter_id = self.get_parameter_id(parameter)
            self.backoff_with_custom_exception(
                self.put_parameter,
                exception=botocore.exceptions.ClientError,
                message_prefix=f"Creating/Updating parameter {parameter_id}",
                max_attempts=5,
                base_delay=1,
                max_delay=10,
                factor=2,
                parameter_id=parameter_id,
                parameter_value=parameter_value,
                tags=[
                    {"Key": "Environment", "Value": self.environment.name},
                    {"Key": "App", "Value": self.name},
                ],
            )

    def push_secrets(self):
        """
        Push all local secrets to AWS Secrets Manager.

        Iterates through flattened local secrets and creates/updates
        corresponding secrets in Secrets Manager. Empty values are stored
        as "__EMPTY__" placeholder.
        """
        for secret, value in self.get_flattened_secrets().items():
            sec_val = str(value)
            if len(sec_val) == 0:
                sec_val = "__EMPTY__"
            secret_id = self.get_secret_id(secret)
            try:
                self.backoff_with_custom_exception(
                    self.create_secret,
                    exception=botocore.exceptions.ClientError,
                    message_prefix=f"Creating/Updating secret {secret_id}",
                    max_attempts=5,
                    base_delay=1,
                    max_delay=10,
                    factor=2,
                    Name=secret_id,
                    SecretString=sec_val,
                    Tags=[
                        {"Key": "Environment", "Value": self.environment.name},
                        {"Key": "App", "Value": self.name},
                    ],
                    ForceOverwriteReplicaSecret=True,
                )

            except Exception as err:
                logger.error(f"Failed to push secret {secret_id}")
                raise err
            self.environment.manager.click.secho(f"Pushed {secret_id}")

    def fetch_secret_value(self, secret):
        """
        Retrieve a secret's value from AWS Secrets Manager.

        Args:
            secret: Secret metadata dict containing 'ARN' key.

        Returns:
            str: The secret value, or empty string if stored as "__EMPTY__".
        """
        response = self.secrets_client.get_secret_value(SecretId=secret["ARN"])
        sec_val = response["SecretString"]
        if sec_val == "__EMPTY__":
            return ""
        return response["SecretString"]

    @property
    def remote_ssm_parameter_filters(self):
        """SSM DescribeParameters filter for this app's parameters."""
        return [
            {
                "Key": "Name",
                "Option": "Contains",
                "Values": [f"/{self.environment.name}/{self.name}"],
            }
        ]

    @property
    def remote_secret_filters(self):
        """Secrets Manager ListSecrets filter for this app's secrets."""
        return [
            {"Key": "tag-key", "Values": ["Environment"]},
            {"Key": "tag-value", "Values": [self.environment.name]},
            {"Key": "tag-key", "Values": ["App"]},
            {"Key": "tag-value", "Values": [self.name]},
        ]

    def get_remote_ssm_parameters(self):
        """
        Fetch all SSM parameters for this app from AWS.

        Returns:
            dict: Parameter metadata keyed by parameter name (without path prefix).
        """
        paginator = self.ssm_client.get_paginator("describe_parameters")
        parameters = {}
        filters = self.remote_ssm_parameter_filters
        response = paginator.paginate(
            ParameterFilters=filters,
        )
        for page in response:
            for parameter in page["Parameters"]:
                parameter_key = os.path.split(parameter["Name"])[-1]
                # parameters.append(parameter_key)
                parameters[parameter_key] = parameter
        return parameters

    def get_remote_secrets(self) -> typing.Dict[str, str]:
        """
        Fetch all secrets for this app from AWS Secrets Manager.

        Returns:
            dict: Secret values keyed by secret name (without path prefix).
        """
        paginator = self.secrets_client.get_paginator("list_secrets")
        secrets = {}
        response = paginator.paginate(
            Filters=self.remote_secret_filters,
        )
        for page in response:
            for secret in page["SecretList"]:
                secret_key = os.path.split(secret["Name"])[-1]
                secrets[secret_key] = self.fetch_secret_value(secret)

        return secrets

    def get_remote_secret_records(self):
        """
        Fetch secret metadata records from AWS Secrets Manager.

        Returns:
            dict: Secret metadata (ARN, name, etc.) keyed by secret name.
        """
        paginator = self.secrets_client.get_paginator("list_secrets")
        secrets = {}
        response = paginator.paginate(
            Filters=self.remote_secret_filters,
        )
        for page in response:
            for secret in page["SecretList"]:
                secret_key = os.path.split(secret["Name"])[-1]
                secrets[secret_key] = secret

        return secrets

    def convert_flatten(self, d, parent_key="", sep="_"):
        """
        Flatten a nested dictionary into a single-level dictionary.

        Nested keys are joined with the separator to form flat keys.
        Example: {"db": {"host": "localhost"}} -> {"db_host": "localhost"}

        Args:
            d: The dictionary to flatten.
            parent_key: Prefix for keys (used in recursion).
            sep: Separator between nested key levels (default: "_").

        Returns:
            dict: Flattened key-value pairs.
        """
        items = []
        if isinstance(d, dict):
            for k, v in d.items():
                new_key = parent_key + sep + k if parent_key else k

                if isinstance(v, MutableMapping):
                    items.extend(self.convert_flatten(v, new_key, sep=sep).items())
                else:
                    items.append((new_key, v))
        return dict(items)


class BootstrapEnvironment:
    """
    Represents a deployment environment containing multiple applications.

    An environment is a directory containing YAML configuration files for
    multiple applications. Each environment typically represents a deployment
    stage (e.g., "production", "staging", "development").

    The environment scans its directory for YAML files and creates BootstrapApp
    instances for each discovered application.

    Directory Structure:
        {environment_name}/
        ├── common.yaml           # Shared config for all apps
        ├── common.secret.yaml    # Shared secrets for all apps
        ├── app1.yaml             # App1 configuration
        ├── app1.secret.yaml      # App1 secrets
        ├── app2.yaml             # App2 configuration
        └── app2.secret.yaml      # App2 secrets

    Args:
        name: Environment name (e.g., "production", "staging").
        path: Local filesystem path to the environment directory.
        manager: Parent BootstrapManager instance.
    """

    manager: BootstrapManager

    def __init__(self, name, path, manager: BootstrapManager):
        self.name = name
        self.path = path
        self.manager = manager
        if self.path:
            self.copy_to_temp()

    @property
    def temp_dir(self):
        """Temporary directory for this environment's file processing."""
        if not hasattr(self, "_temp_dir"):
            self._temp_dir = os.path.join(self.manager.temp_dir, self.name)
            os.mkdir(self._temp_dir)
        return self._temp_dir

    @property
    def apps(self) -> typing.Dict[str, BootstrapApp]:
        """
        Dictionary of BootstrapApp instances for all apps in this environment.

        Scans the environment directory for .yaml/.yml files and creates
        BootstrapApp instances. Secret files (.secret.yaml) are excluded
        from this list as they're accessed via their parent app.

        Returns:
            dict: App name -> BootstrapApp mapping.
        """
        if not hasattr(self, "_apps"):
            self._apps = {}
            for file in os.listdir(self.path):
                absolute_path = os.path.join(self.path, file)
                app_name, file_extension = os.path.splitext(file)
                app_name, is_secret = os.path.splitext(app_name)

                if (
                    os.path.isfile(absolute_path)
                    and file_extension in [".yaml", ".yml"]
                    and not is_secret
                ):
                    self._apps[app_name] = BootstrapApp(
                        app_name, absolute_path, environment=self
                    )
        return self._apps

    def copy_to_temp(self):
        """Copy all app configuration files to the temporary directory."""
        for _app_name, app in self.apps.items():
            shutil.copy(app.path, self.temp_dir)


class BootstrapManager:
    """
    Central orchestrator for bootstrap configuration operations.

    The BootstrapManager coordinates all bootstrap activities including:
    - AWS client management (S3, SSM, Secrets Manager)
    - Environment and application discovery
    - Configuration push/pull operations
    - Cleanup of orphaned resources

    This is the main entry point for programmatic use of the bootstrap system.
    It manages lazy-loaded AWS clients and provides access to all environments
    and applications within a configuration directory.

    Architecture:
        BootstrapManager
        └── BootstrapEnvironment (one per environment directory)
            └── BootstrapApp (one per YAML file)

    Args:
        prefix: SSM parameter path prefix (e.g., "/appconfig").
        region: AWS region for all operations.
        click: Click module for CLI output.
        values_path: Local directory containing environment subdirectories.
        bucket_name: S3 bucket for storing configuration files.
        endpoint_url: Custom AWS endpoint URL (for testing with LocalStack).

    Example:
        >>> manager = BootstrapManager(
        ...     prefix="/appconfig",
        ...     region="eu-west-2",
        ...     click=click,
        ...     values_path="./config",
        ...     bucket_name="app-bootstrap-123456789"
        ... )
        >>> manager.put_config(delete_first=True)
    """

    _environments: dict[str, BootstrapEnvironment]

    def __init__(
        self,
        prefix,
        region,
        click,
        values_path,
        bucket_name,
        endpoint_url=AWS_ENDPOINT_URL,
    ):
        self.prefix = prefix
        self.region = region
        self.click = click
        self.values_path = values_path
        self.endpoint_url = endpoint_url
        self.bucket_name = bucket_name

    @property
    def s3_client(self) -> S3Client:
        """Lazily instantiated AWS S3 client."""
        if not hasattr(self, "_s3_client"):
            self._s3_client = boto3.client(
                "s3", region_name=self.region, endpoint_url=self.endpoint_url
            )
        return self._s3_client

    @property
    def ssm_client(self):
        """Lazily instantiated AWS SSM client."""
        if not hasattr(self, "_ssm_client"):
            self._ssm_client = boto3.client(
                "ssm", region_name=self.region, endpoint_url=self.endpoint_url
            )
        return self._ssm_client

    @property
    def secrets_client(self) -> SecretsManagerClient:
        """Lazily instantiated AWS Secrets Manager client."""
        if not hasattr(self, "_secrets_client"):
            self._secrets_client = boto3.client(
                "secretsmanager",
                region_name=self.region,
                endpoint_url=self.endpoint_url,
            )
        return self._secrets_client

    @property
    def values_path_real(self):
        """Resolved absolute path to the values directory."""
        return os.path.realpath(self.values_path)

    @property
    def temp_dir(self):
        """Temporary directory for file processing operations."""
        if not hasattr(self, "_temp_dir"):
            self._temp_dir = tempfile.TemporaryDirectory("app-bootstrap")
        return self._temp_dir.name

    def initBootstrap(self):
        """
        Initialize the bootstrap infrastructure by creating the S3 bucket.

        Creates a private S3 bucket for storing configuration files.
        Handles cases where the bucket already exists.
        """
        try:
            self.s3_client.create_bucket(
                ACL="private",
                Bucket=f"{self.bucket_name}",
                CreateBucketConfiguration={"LocationConstraint": self.region},
            )
        except self.s3_client.exceptions.BucketAlreadyOwnedByYou:
            self.click.secho(
                f"Already initialised with bucket {self.bucket_name}",
                bg="red",
                fg="white",
            )
        except self.s3_client.exceptions.BucketAlreadyExists:
            self.click.secho(
                f"Bucket {self.bucket_name} already exists but is not owned by you.",
                bg="red",
                fg="white",
            )
        except Exception as err:
            self.click.secho(f"S3 Client Error {err}", bg="red", fg="white")

    def put_config(self, delete_first):
        """
        Push all local configuration to AWS.

        For each environment and application:
        1. Cleans up orphaned SSM parameters and secrets
        2. Uploads YAML files to S3
        3. Pushes parameters to SSM Parameter Store
        4. Pushes secrets to Secrets Manager

        Args:
            delete_first: Whether to delete orphaned resources before pushing.
        """
        self.cleanup_ssm_parameters()
        self.cleanup_secrets()
        for _environment_name, environment in self.environments.items():
            for _app_name, app in environment.apps.items():
                # pass
                app.upload_to_s3()
                app.push_parameters()
                app.push_secrets()

    def cleanup_ssm_parameters(self):
        """Remove orphaned SSM parameters across all environments and apps."""
        for _environment_name, environment in self.environments.items():
            for _app_name, app in environment.apps.items():
                app.cleanup_ssm_parameters()

    def cleanup_secrets(self):
        """Remove orphaned secrets across all environments and apps."""
        for _environment_name, environment in self.environments.items():
            for _app_name, app in environment.apps.items():
                app.cleanup_secrets()

    @property
    def environments(self) -> typing.Dict[str, BootstrapEnvironment]:
        """
        Dictionary of all BootstrapEnvironment instances.

        Scans the values_path directory for subdirectories and creates
        a BootstrapEnvironment for each.

        Returns:
            dict: Environment name -> BootstrapEnvironment mapping.
        """
        if not hasattr(self, "_environments"):
            self._environments = {}
            for item in os.listdir(self.values_path_real):
                if os.path.isdir(os.path.join(self.values_path_real, item)):
                    if item not in self._environments:
                        self._environments[item] = BootstrapEnvironment(
                            item,
                            os.path.join(self.values_path_real, item),
                            manager=self,
                        )

        return self._environments

    def list_apps(self):
        """
        List all applications stored in S3 across all environments.

        Returns:
            dict: Environment name -> list of app names mapping.
        """
        paginator = self.s3_client.get_paginator("list_objects")
        response_iterator = paginator.paginate(
            Bucket=self.bucket_name,
        )
        items = {}
        for page in response_iterator:
            for item in page["Contents"]:
                envname, filename = item["Key"].split("/")
                if envname not in items:
                    items[envname] = []
                items[envname].append(os.path.splitext(filename)[0])
        return items
