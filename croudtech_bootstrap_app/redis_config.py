import redis
import json
from .metrics import Metrics


class RedisConfig:
    _redis_dbs = {}
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
        if not hasattr(self, "_strict_redis"):
            self._strict_redis = redis.StrictRedis(
                host=self._redis_host, port=self._redis_port
            )
        return self._strict_redis

    @property
    def redis_config(self):
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
        return json.loads(self.redis_config.get(self._allocated_dbs_key))

    @property
    def db_key(self):
        return "%s_%s" % (self._environment, self._app_name)

    def get_redis_database(self, allocate=False):
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
        unused_dbs = self.get_unused_dbs()
        db = unused_dbs[0]
        db_config = self.redis_db_allocations
        db_config[self.db_key] = db
        self._redis_config.set(self._allocated_dbs_key, json.dumps(db_config))

        return db

    def deallocate_db(self):
        unused_dbs = self.get_unused_dbs()        
        db_config = self.redis_db_allocations
        if self.db_key in db_config:
            db = db_config[self.db_key]
            del(db_config[self.db_key])
            self._redis_config.set(self._allocated_dbs_key, json.dumps(db_config))

            return True, db
        return False, None

    def get_redis_allocated_db(self, db):
        if db not in self._redis_dbs:
            self._redis_dbs[db] = redis.Redis(
                host=self._redis_host, port=self._redis_port, db=db
            )
        return self._redis_dbs[db]

    def get_unused_dbs(self):
        possible_dbs = range(0, 15)
        return list(
            set(possible_dbs)
            - set([int(i) for i in self.redis_db_allocations.values()])
        )

    def get_databases(self):
        return self.strict_redis.config_get("databases")

    def get_keyspace(self):
        return self.strict_redis.info("keyspace")
