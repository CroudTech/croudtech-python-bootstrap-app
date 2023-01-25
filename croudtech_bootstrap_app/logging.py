import logging
import os
import sys


def init():
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, os.getenv("LOG_LEVEL", "INFO")))
    handler = logging.StreamHandler(sys.stdout)
    # handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logging.getLogger("boto3").setLevel(logging.CRITICAL)
    logging.getLogger("botocore").setLevel(logging.CRITICAL)
    logging.getLogger("s3transfer").setLevel(logging.CRITICAL)
    logging.getLogger("urllib3").setLevel(logging.CRITICAL)
    return logger
