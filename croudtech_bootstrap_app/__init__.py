import os

from croudtech_bootstrap_app.logging import init as initLogs

__version__ = "0.0.0"

logger = initLogs()

if not os.getenv("AWS_DEFAULT_REGION", False) and not os.getenv("AWS_REGION", False):
    logger.info("Setting default region to eu-west-2")
    os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-2")
