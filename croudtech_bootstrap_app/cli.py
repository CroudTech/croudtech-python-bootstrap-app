import json
import os
import urllib.parse
import boto3
import click
from table2ascii import Alignment, table2ascii
from yaml import dump

from .bootstrap import BootstrapManager, BootstrapParameters
from .redis_config import RedisConfig

from http.server import BaseHTTPRequestHandler, HTTPServer


try:
    from yaml import CDumper as Dumper
except ImportError:
    from yaml import Dumper


def object2table(object):
    col1width = len(max(object.keys(), key=len))
    col2width = len(str(max(object.values())))
    headfoot = "+-%s-+-%s-+" % ("-" * col1width, "-" * col2width)
    lines = [headfoot]
    for k, v in object.items():
        col1pad = " " * (col1width - len(str(k)))
        col2pad = " " * (col2width - len(str(v)))
        lines.append("| %s%s | %s%s |" % (k, col1pad, v, col2pad))
    lines.append(headfoot)
    return "\n".join(lines)


@click.group()
@click.option(
    "--endpoint-url",
    default=os.getenv("AWS_ENDPOINT_URL", None),
    help="The AWS API endpoint URL",
)
@click.option(
    "--put-metrics",
    default=True,
    help="Use Cloudwatch Metrics to track usage",
)
@click.option(
    "--bucket-name",
    default=f"app-bootstrap-{boto3.client('sts').get_caller_identity().get('Account')}",
)
@click.pass_context
def cli(ctx, endpoint_url, put_metrics, bucket_name):
    # ensure that ctx.obj exists and is a dict (in case `cli()` is called
    # by means other than the `if` block below)
    ctx.ensure_object(dict)

    ctx.obj["AWS_ENDPOINT_URL"] = endpoint_url
    if ctx.obj["AWS_ENDPOINT_URL"]:
        click.echo(
            click.style(
                "Using aws endpoint url %s" % ctx.obj["AWS_ENDPOINT_URL"],
                blink=True,
                bold=True,
            )
        )

    ctx.obj["PUT_METRICS"] = put_metrics
    ctx.obj["BUCKET_NAME"] = bucket_name


@cli.command()
@click.pass_context
@click.option("--environment-name", help="The environment name", required=True)
@click.option("--region", default="eu-west-2", help="The AWS region")
def init(ctx, environment_name, region):
    bootstrap_manager = BootstrapManager(
        prefix=None,
        region=region,
        click=click,
        values_path=None,
        bucket_name=ctx.obj["BUCKET_NAME"],
        endpoint_url=ctx.obj["AWS_ENDPOINT_URL"],
    )
    bootstrap_manager.initBootstrap()


@cli.command()
@click.pass_context
@click.option("--environment-name", help="The environment name", required=True)
@click.option("--app-name", help="The app name", required=True)
@click.option("--prefix", default="/appconfig", help="The path prefix")
@click.option("--region", default="eu-west-2", help="The AWS region")
@click.option(
    "--include-common/--ignore-common",
    default=True,
    is_flag=True,
    help="Include shared variables",
)
@click.option(
    "--output-format",
    default="json",
    type=click.Choice(["json", "yaml", "environment", "environment-export"]),
)
@click.option(
    "--parse-redis-param/--ignore-redis-param",
    default=True,
    is_flag=True,
    help="Parse redis host and allocate a redis database number",
)
def get_config(
    ctx,
    environment_name,
    app_name,
    prefix,
    region,
    include_common,
    output_format,
    parse_redis_param,
):
    bootstrap = BootstrapParameters(
        environment_name=environment_name,
        app_name=app_name,
        prefix=prefix,
        region=region,
        include_common=include_common,
        click=click,
        endpoint_url=ctx.obj["AWS_ENDPOINT_URL"],
        parse_redis=parse_redis_param,
        bucket_name=ctx.obj["BUCKET_NAME"],
    )
    output = "Invalid output format"

    if output_format == "json":
        output = json.dumps(bootstrap.get_raw_params(), indent=2)
    elif output_format == "yaml":
        output = dump(bootstrap.get_raw_params(), Dumper=Dumper)
    elif output_format == "environment":
        output = bootstrap.params_to_env()
    elif output_format == "environment-export":
        output = bootstrap.params_to_env(export=True)

    if isinstance(output, str):
        print(output)


@cli.command()
@click.pass_context
@click.option("--environment-name", help="The environment name", required=True)
@click.option("--app-name", help="The app name", required=True)
@click.option("--prefix", default="/appconfig", help="The path prefix")
@click.option("--region", default="eu-west-2", help="The AWS region")
@click.option(
    "--include-common/--ignore-common",
    default=True,
    is_flag=True,
    help="Include shared variables",
)
@click.option(
    "--output-format",
    default="json",
    type=click.Choice(["json", "yaml", "environment", "environment-export"]),
)
@click.option(
    "--parse-redis-param/--ignore-redis-param",
    default=True,
    is_flag=True,
    help="Parse redis host and allocate a redis database number",
)
@click.option(
    "--server-port",
    default="9099"
)
def config_server(
    ctx,
    environment_name,
    app_name,
    prefix,
    region,
    include_common,
    output_format,
    parse_redis_param,
    server_port
):
    bootstrap = BootstrapParameters(
        environment_name=environment_name,
        app_name=app_name,
        prefix=prefix,
        region=region,
        include_common=include_common,
        click=click,
        endpoint_url=ctx.obj["AWS_ENDPOINT_URL"],
        parse_redis=parse_redis_param,
        bucket_name=ctx.obj["BUCKET_NAME"],
    )

    class ConfigServer(BaseHTTPRequestHandler):     
        def do_GET(self):            
            if output_format == "json":
                # self.send_header("Content-type", "text/json")
                output = json.dumps(bootstrap.get_raw_params(), indent=2)
            elif output_format == "yaml":
                # self.send_header("Content-type", "text/yaml")
                output = dump(bootstrap.get_raw_params(), Dumper=Dumper)
            elif output_format == "environment":
                # self.send_header("Content-type", "text/plain")
                output = bootstrap.params_to_env()
            elif output_format == "environment-export":
                # self.send_header("Content-type", "text/plain")
                output = bootstrap.params_to_env(export=True)

            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            for line in output.split("\n"):
                self.wfile.write(bytes(line + "\n", "utf-8"))
            # raise KeyboardInterrupt()
            
    
    webServer = HTTPServer(("0.0.0.0", int(server_port)), ConfigServer)
    print("Server started http://%s:%s" % ("0.0.0.0", server_port))
    try:
        webServer.serve_forever()
    except KeyboardInterrupt:
        pass

    webServer.server_close()
    print("Server stopped.")


@cli.command()
@click.pass_context
@click.option("--prefix", default="/appconfig", help="The path prefix")
@click.option("--region", default="eu-west-2", help="The AWS region")
@click.option(
    "--delete-first",
    is_flag=True,
    default=False,
    help="Delete the values in this path before pushing (useful for cleanup)",
)
@click.argument("values_path")
def put_config(ctx, prefix, region, delete_first, values_path):
    bootstrap_manager = BootstrapManager(
        prefix=prefix,
        region=region,
        click=click,
        values_path=values_path,
        bucket_name=ctx.obj["BUCKET_NAME"],
        endpoint_url=ctx.obj["AWS_ENDPOINT_URL"],
    )

    bootstrap_manager.put_config(delete_first=delete_first)


@cli.command()
@click.pass_context
@click.option("--prefix", default="/appconfig", help="The path prefix")
@click.option("--region", default="eu-west-2", help="The AWS region")
@click.option(
    "--delete-first",
    is_flag=True,
    default=False,
    help="Delete the values in this path before pushing (useful for cleanup)",
)
@click.argument("values_path")
def cleanup_secrets(ctx, prefix, region, delete_first, values_path):
    bootstrap_manager = BootstrapManager(
        prefix=prefix,
        region=region,
        click=click,
        values_path=values_path,
        bucket_name=ctx.obj["BUCKET_NAME"],
        endpoint_url=ctx.obj["AWS_ENDPOINT_URL"],
    )

    bootstrap_manager.cleanup_secrets()


@cli.command()
@click.pass_context
@click.option("--prefix", default="/appconfig", help="The path prefix")
@click.option("--region", default="eu-west-2", help="The AWS region")
def list_apps(ctx, prefix, region):
    bootstrap_manager = BootstrapManager(
        prefix=prefix,
        region=region,
        click=click,
        values_path=None,
        bucket_name=ctx.obj["BUCKET_NAME"],
        endpoint_url=ctx.obj["AWS_ENDPOINT_URL"],
    )
    table = []
    for environment, apps in bootstrap_manager.list_apps().items():
        for app in apps:
            table.append([environment, app])
    output = table2ascii(
        header=["Environment", "App"],
        body=table,
        alignments=[Alignment.LEFT] + [Alignment.LEFT],
    )

    click.secho(output, fg="cyan")


@cli.group()
def manage_redis():
    """Redis DB Allocation Management"""
    pass


@manage_redis.command()
@click.pass_context
@click.option("--environment-name", help="The environment name", required=True)
@click.option("--app-name", help="The app name", required=True)
@click.option("--prefix", default="/appconfig", help="The path prefix")
@click.option("--region", default="eu-west-2", help="The AWS region")
@click.option(
    "--include-common/--ignore-common",
    default=True,
    is_flag=True,
    help="Include shared variables",
)
def show_db(ctx, environment_name, app_name, prefix, region, include_common):
    """Show Allocated Redis Database for a specified application"""
    bootstrap = BootstrapParameters(
        environment_name=environment_name,
        app_name=app_name,
        prefix=prefix,
        region=region,
        include_common=include_common,
        click=click,
        endpoint_url=ctx.obj["AWS_ENDPOINT_URL"],
        parse_redis=True,
        bucket_name=ctx.obj["BUCKET_NAME"],
    )
    redis_db, redis_host, redis_port = bootstrap.get_redis_db()
    click.echo(
        "Redis config: Db: %s, Host: %s, Port: %s" % (redis_db, redis_host, redis_port)
    )


@manage_redis.command()
@click.pass_context
@click.option("--redis-host", help="The redis host", required=True)
@click.option("--redis-port", help="The redis port", required=True, default=6379)
def show_dbs(ctx, redis_host, redis_port):
    """Show all allocated Redis databases"""
    redis_config_instance = RedisConfig(
        redis_host=redis_host,
        redis_port=redis_port,
        app_name="Undefined",
        environment="Undefined",
        put_metrics=False,
    )
    click.secho(object2table(redis_config_instance.redis_db_allocations), fg="cyan")


@manage_redis.command()
@click.pass_context
@click.option("--redis-host", help="The redis host", required=True)
@click.option("--redis-port", help="The redis port", required=True, default=6379)
@click.option("--environment-name", help="The environment name", required=True)
@click.option("--app-name", help="The application name", required=True)
def allocate_db(ctx, redis_host, redis_port, environment_name, app_name):
    """Allocate a Redis database for a specified application and environment"""
    redis_config_instance = RedisConfig(
        redis_host=redis_host,
        redis_port=redis_port,
        app_name=app_name,
        environment=environment_name,
        put_metrics=False,
    )
    db = redis_config_instance.allocate_db()
    click.secho(
        "Allocated Database %s to %s/%s" % (db, environment_name, app_name), fg="green"
    )
    click.secho(object2table(redis_config_instance.redis_db_allocations), fg="cyan")


@manage_redis.command()
@click.pass_context
@click.option("--redis-host", help="The redis host", required=True)
@click.option("--redis-port", help="The redis port", required=True, default=6379)
@click.option("--environment-name", help="The environment name", required=True)
@click.option("--app-name", help="The application name", required=True)
def deallocate_db(ctx, redis_host, redis_port, environment_name, app_name):
    """Remove Redis database allocation for the specified application and environment"""
    redis_config_instance = RedisConfig(
        redis_host=redis_host,
        redis_port=redis_port,
        app_name=app_name,
        environment=environment_name,
        put_metrics=False,
    )
    success, db = redis_config_instance.deallocate_db()
    if success:
        click.secho(
            "DeAllocated Database %s from %s/%s" % (db, environment_name, app_name),
            fg="green",
        )
        click.secho("Allocated Databases:", fg="white")
        click.secho(object2table(redis_config_instance.redis_db_allocations), fg="cyan")
    else:
        click.secho(
            "No Database was allocated to %s/%s" % (environment_name, app_name),
            fg="red",
            bold=True,
        )
        click.secho("Allocated Databases:", fg="white")
        click.secho(object2table(redis_config_instance.redis_db_allocations), fg="cyan")


if __name__ == "__main__":
    cli()
