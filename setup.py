import os

from setuptools import setup

with open(os.path.join(os.getcwd(), "requirements.txt")) as f:
    required = f.read().splitlines()

setup(
    name="croudtech-bootstrap",
    version="0.1.42",
    install_requires=required,
)
