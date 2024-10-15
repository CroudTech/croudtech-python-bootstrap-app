#!/bin/bash
set -e

if git diff --exit-code origin/main VERSION; then
  bump2version --allow-dirty patch VERSION --current-version `cat VERSION`
fi
