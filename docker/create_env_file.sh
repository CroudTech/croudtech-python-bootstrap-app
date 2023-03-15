#!/bin/bash

croudtech-bootstrap get-config --environment-name $CONFIG_ENVIRONMENT --app-name $APPNAME --output-format=environment $CONFIG_ARGS > ./.env