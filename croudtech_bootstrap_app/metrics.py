import boto3

cloudwatch = boto3.client("cloudwatch")


class Metrics:
    def put_redis_db_metric(self, app_key, redis_db, redis_host, environment_name):
        try:
            cloudwatch.put_metric_data(
                MetricData=[
                    {
                        "MetricName": "Redis DB Allocations",
                        "Dimensions": [
                            {"Name": "REDIS_HOST", "Value": redis_host},
                            {"Name": "APP_KEY", "Value": app_key},
                        ],
                        "Unit": "None",
                        "Value": redis_db,
                    },
                ],
                Namespace="%s/RedisDbAllocations" % environment_name,
            )
        except Exception as err:
            print(err)
