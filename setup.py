from setuptools import setup
import os
with open(os.path.join(os.getcwd(), "requirements.txt")) as f:
    required = f.read().splitlines()

setup(name='croudtech-bootstrap',
    version=os.getenv("SEMVER", os.getenv("GitVersion_FullSemVer", "dev")),
)

