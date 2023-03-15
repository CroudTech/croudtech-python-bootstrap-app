import * as cdk from "aws-cdk-lib";
import { IRepository, Repository, TagStatus } from "aws-cdk-lib/aws-ecr";
import { DockerImageAsset } from "aws-cdk-lib/aws-ecr-assets";
import { StringParameter } from "aws-cdk-lib/aws-ssm";
import * as ecrdeploy from "cdk-ecr-deployment";
import { Construct } from "constructs";
import * as path from "path";

interface BaseProps extends cdk.StackProps {
    organisation: string;
    department: string;
    environment: string;
    app_name: string;
    repository_name: string;
}

// import * as sqs from 'aws-cdk-lib/aws-sqs';
interface BuildStackProps extends BaseProps {
    tag: string;
    git_access_token: string;
}
export class BuildStack extends cdk.Stack {
    protected _repository: IRepository;
    protected _image: DockerImageAsset;
    protected git_access_token: string;
    protected props: BuildStackProps;
    constructor(scope: Construct, id: string, props: BuildStackProps) {
        super(scope, id, props);
        this.props = props;
        this.git_access_token = props.git_access_token;
        new ecrdeploy.ECRDeployment(this, "DeployDockerImage", {
            src: new ecrdeploy.DockerImageName(this.image.imageUri),
            dest: new ecrdeploy.DockerImageName(
                this.repository.repositoryUriForTag(props.tag)
            ),
        });

        cdk.Tags.of(this).add("Organisation", props.organisation);
        cdk.Tags.of(this).add("Department", props.department);
        cdk.Tags.of(this).add("Environment", props.environment);
        cdk.Tags.of(this).add("CfStackName", this.stackName);
        cdk.Tags.of(this).add("sst:app", props.app_name);
    }

    public get image(): DockerImageAsset {
        if (this._image == undefined) {
            this._image = new DockerImageAsset(this, "DockerImageAsset", {
                directory: path.dirname(path.dirname(__dirname)),
                file: "DockerfileEcs",
                buildArgs: {
                    GIT_ACCESS_TOKEN: this.git_access_token,
                },
            });
        }
        return this._image;
    }

    public get repository(): IRepository {
        if (this._repository == undefined) {
            this._repository = Repository.fromRepositoryName(
                this,
                "ApplicationEcrRepository",
                this.props.repository_name
            );
        }
        return this._repository;
    }
}

interface InitStackProps extends BaseProps {}

export class InitStack extends cdk.Stack {
    protected _repository: Repository;
    protected _image: DockerImageAsset;
    protected git_access_token: string;
    protected props: InitStackProps;

    constructor(scope: Construct, id: string, props: InitStackProps) {
        super(scope, id, props);
        this.props = props;
        this.repository;

        cdk.Tags.of(this).add("Organisation", props.organisation);
        cdk.Tags.of(this).add("Department", props.department);
        cdk.Tags.of(this).add("Environment", props.environment);
        cdk.Tags.of(this).add("CfStackName", this.stackName);
        cdk.Tags.of(this).add("sst:app", props.app_name);
    }

    public get repository(): Repository {
        if (this._repository == undefined) {
            this._repository = new Repository(
                this,
                "ApplicationEcrRepository",
                {
                    repositoryName: this.props.repository_name,
                    lifecycleRules: [
                        {
                            description: "Delete untagged images",
                            tagStatus: TagStatus.UNTAGGED,
                            maxImageCount: 1,
                        },
                    ],
                }
            );
        }
        return this._repository;
    }
}

interface ReleaseStackProps extends BaseProps {
    tag: string;
}
export class ReleaseStack extends cdk.Stack {
    protected _image: DockerImageAsset;
    protected git_access_token: string;
    protected _repository: IRepository;
    protected props: ReleaseStackProps;
    constructor(scope: Construct, id: string, props: ReleaseStackProps) {
        super(scope, id, props);
        this.props = props;
        const config_environment =
            props.environment.charAt(0).toUpperCase() +
            props.environment.slice(1);
        const version_parameter = new StringParameter(
            this,
            "VersionParameter",
            {
                parameterName: `/Application/CroudControl/${config_environment}/${props.app_name}/Version`,
                stringValue: props.tag,
            }
        );

        new ecrdeploy.ECRDeployment(this, "DeployDockerImage", {
            src: new ecrdeploy.DockerImageName(
                this.repository.repositoryUriForTag(props.tag)
            ),
            dest: new ecrdeploy.DockerImageName(
                this.repository.repositoryUriForTag(
                    "deployed_to_" + props.environment
                )
            ),
        });

        cdk.Tags.of(this).add("Organisation", props.organisation);
        cdk.Tags.of(this).add("Department", props.department);
        cdk.Tags.of(this).add("Environment", props.environment);
        cdk.Tags.of(this).add("CfStackName", this.stackName);
        cdk.Tags.of(this).add("sst:app", props.app_name);
    }

    public get repository(): IRepository {
        if (this._repository == undefined) {
            this._repository = Repository.fromRepositoryName(
                this,
                "ApplicationEcrRepository",
                this.props.repository_name
            );
        }
        return this._repository;
    }
}
