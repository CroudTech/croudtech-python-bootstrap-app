#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { InitStack, ReleaseStack } from "../lib/cdk-stack";
import { BuildStack } from "./../lib/cdk-stack";
import * as AWS from "aws-sdk";

const organisation = process.env["ORGANISATION"] || "CroudTech";
const department = process.env["DEPARTMENT"] || "CroudControl";
const environment = process.env["ENVIRONMENT"] || "Local";
const tag = process.env["SEMVER"] || "dev";
const app_name = "ConfigSidecar";
const repository = "croudcontrol/config-sidecar";

const app = new cdk.App();
if (environment == "Shared") {
    new InitStack(app, "InitStack", {
        organisation,
        department,
        environment: "Shared",
        app_name: app_name,
        stackName: [`${app_name}Initialise`, "Shared"].join("-"),
        repository_name: repository,
    });
}

if (["Integration", "Prelive", "Production"].includes(environment)) {
    if (process.env.PIPELINE_TYPE == "build") {
        var secretsmanager = new AWS.SecretsManager();
        secretsmanager.getSecretValue(
            {
                SecretId: "config_update_github_access_token",
            },
            function (err, data) {
                if (err) console.log(err, err.stack); // an error occurred
                else {
                    new BuildStack(app, "BuildStack", {
                        organisation,
                        department,
                        environment,
                        app_name: app_name,
                        tag: tag,
                        git_access_token: data.SecretString || "",
                        stackName: [`${app_name}Build`, environment].join("-"),
                        repository_name: repository,
                    });
                }
            }
        );
    } else {
        new ReleaseStack(app, "ReleaseStack", {
            organisation,
            department,
            environment,
            app_name: app_name,
            tag: tag,
            stackName: [`${app_name}Release`, environment].join("-"),
            repository_name: repository,
        });
    }
}
