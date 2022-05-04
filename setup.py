from setuptools import setup

with open("requirements.txt") as f:
    required = f.read().splitlines()

setup(name='croudtech-bootstrap',
      install_requires=required,
      packages=['croudtech_bootstrap_app'],
      entry_points={
          "console_scripts": [
              "croudtech-bootstrap=croudtech_bootstrap_app.cli:cli"
          ],
      },)
