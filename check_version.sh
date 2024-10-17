#!/bin/bash
set -e
export VERSION=$(poetry version --short)
echo "Current version is $VERSION"
if git diff --exit-code origin/main $VERSION; then
  echo "Please bump version in pyproject.toml"
  exit 1
else
  echo "Basic version check ok"
fi
