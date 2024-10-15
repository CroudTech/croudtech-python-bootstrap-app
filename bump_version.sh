#!/bin/bash
set -e

if git diff --exit-code origin/master VERSION; then
  bump2version --allow-dirty patch VERSION --current-version `cat VERSION`
fi
