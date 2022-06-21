# -*- mode: python ; coding: utf-8 -*-
os.environ["AWS_DEFAULT_REGION"]="eu-west-2"

from croudtech_bootstrap_app.cli import cli
import os

os.environ["LC_ALL"]="C.UTF-8"
os.environ["LANG"]="C.UTF-8"

cli()