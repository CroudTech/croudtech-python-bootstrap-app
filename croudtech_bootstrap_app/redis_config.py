"""
Redis database allocation management for multi-tenant applications.

This module provides automatic Redis database allocation for applications
sharing a single Redis instance. Each application is assigned a unique
database number (0-14) to ensure data isolation.

Database 15 is reserved for storing allocation metadata.
"""

import json
from typing import Dict

import redis

from .metrics import Metrics


class RedisConfig:
    """
    Manages Redis database allocation for multi-tenant environments.

    In a shared Redis instance, multiple applications need isolated databases.
    This class tracks which database numbers are allocated to which applications
    and provides automatic allocation of available databases.

    Database Allocation:
        - Databases 0-14 are available for applications
        - Database 15 is reserved for storing allocation metadata
        - Allocations are stored as JSON in the 'allocated_dbs' key

    Allocation Key Format:
        Applications are identified by "{environment}_{app_name}" keys.
        For example: "production_myapp" -> database 3

    Usage:
        When REDIS_DB is set to "auto" in an application's configuration,
        the bootstrap system will automatically allocate a database using
        this class.

    Args:
        redis_host: Redis server hostname or IP.
        redis_port: Redis server port (default: 6379).
        app_name: Application name for allocation tracking.
        environment: Environment name for allocation tracking.
        put_metrics: Whether to publish CloudWatch metrics (default: True).

    Example:
        >>> config = RedisConfig(
        ...     redis_host="localhost",
        ...     redis_port=6379,
        ...     app_name="myapp",
        ...     environment="production"
        ... )
        >>> db_number = config.get_redis_database(allocate=True)
        >>> print(f"Using Redis database {db_number}")
    """

    _redis_dbs: Dict[int, redis.Redis] = {}
    _config_db = 15
    _allocated_dbs_key = "allocated_dbs"

    def __init__(self, redis_host, redis_port, app_name, environment, put_metrics=True):
        self._redis_host = redis_host
        self._redis_port = redis_port
        self._app_name = app_name
        self._environment = environment
        self.put_metrics = put_metrics
        self.metrics = Metrics()

    @property
    def strict_redis(self):
        """StrictRedis client for general Redis operations."""
        if not hasattr(self, "_strict_redis"):
            self._strict_redis = redis.StrictRedis(
                host=self._redis_host, port=self._redis_port
            )
        return self._strict_redis

    @property
    def redis_config(self):
        """
        Redis client connected to the config database (DB 15).

        Initializes the allocation tracking structure if it doesn't exist.
        """
        if not hasattr(self, "_redis_config"):
            self._redis_config = redis.Redis(
                host=self._redis_host, port=self._redis_port, db=self._config_db
            )
            self._redis_config.set("_is_config", 1)
            if self._redis_config.get(self._allocated_dbs_key) is None:
                self._redis_config.set(
                    self._allocated_dbs_key, json.dumps({"self": self._config_db})
                )
        return self._redis_config

    @property
    def redis_db_allocations(self):
        """Current database allocation map: {app_key: db_number}."""
        return json.loads(self.redis_config.get(self._allocated_dbs_key))

    @property
    def db_key(self):
        """Unique key for this app/environment: "{environment}_{app_name}"."""
        return "%s_%s" % (self._environment, self._app_name)

    def get_redis_database(self, allocate=False):
        """
        Get the allocated database number for this application.

        Args:
            allocate: If True, allocate a new database if one doesn't exist.

        Returns:
            int or None: The database number, or None if not allocated.
        """
        allocated_dbs = self.redis_db_allocations
        if self.db_key not in allocated_dbs and allocate:
            allocated_db = self.allocate_db()
        elif self.db_key in allocated_dbs:
            allocated_db = allocated_dbs[self.db_key]
        else:
            allocated_db = None
        if self.put_metrics:
            self.metrics.put_redis_db_metric(
                app_key=self.db_key,
                redis_db=allocated_db,
                redis_host=self._redis_host,
                environment_name=self._environment,
            )
        return allocated_db

    def allocate_db(self):
        """
        Allocate the next available database to this application.

        Returns:
            int: The newly allocated database number.

        Raises:
            IndexError: If no databases are available (all 0-14 are allocated).
        """
        unused_dbs = self.get_unused_dbs()
        db = unused_dbs[0]
        db_config = self.redis_db_allocations
        db_config[self.db_key] = db
        self._redis_config.set(self._allocated_dbs_key, json.dumps(db_config))

        return db

    def deallocate_db(self):
        """
        Remove the database allocation for this application.

        Returns:
            tuple: (success: bool, db_number: int or None)
        """
        self.get_unused_dbs()
        db_config = self.redis_db_allocations
        if self.db_key in db_config:
            db = db_config[self.db_key]
            del db_config[self.db_key]
            self._redis_config.set(self._allocated_dbs_key, json.dumps(db_config))

            return True, db
        return False, None

    def get_redis_allocated_db(self, db):
        """
        Get a Redis client connected to a specific database.

        Args:
            db: Database number to connect to.

        Returns:
            redis.Redis: Client connected to the specified database.
        """
        if db not in self._redis_dbs:
            self._redis_dbs[db] = redis.Redis(
                host=self._redis_host, port=self._redis_port, db=db
            )
        return self._redis_dbs[db]

    def get_unused_dbs(self):
        """
        Get list of unallocated database numbers.

        Returns:
            list: Available database numbers (from 0-14).
        """
        possible_dbs = range(0, 15)
        return list(
            set(possible_dbs)
            - set([int(i) for i in self.redis_db_allocations.values()])
        )

    def get_databases(self):
        """Get Redis server database configuration."""
        return self.strict_redis.config_get("databases")

    def get_keyspace(self):
        """Get Redis keyspace statistics for all databases."""
        return self.strict_redis.info("keyspace")
