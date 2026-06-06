
import pulumi
import pulumi_docker as docker
import pulumi_gcp as gcp

from keycloak import create_keycloak_service

# Initialize Pulumi Configuration
config = pulumi.Config()

neon_database_url = config.require_secret("neonDatabaseUrl")

REGION = "europe-west3"

siteflow_registry = gcp.artifactregistry.Repository(
    "siteflow-registry",
    repository_id="siteflow",
    description="siteflow platform images",
    format="DOCKER",
    location=REGION,
)

placeholder_image_url = pulumi.Output.all(
    siteflow_registry.location, siteflow_registry.project, siteflow_registry.repository_id
).apply(
    lambda args: f"{args[0]}-docker.pkg.dev/{args[1]}/{args[2]}/siteflow-placeholder:latest"
)


placeholder_docker_image = docker.Image(
    "placeholder-custom-image",
    build=docker.DockerBuildArgs(
        context="./placeholderService",
        dockerfile="./placeholderService/Dockerfile",
        platform="linux/amd64",
    ),
    image_name=placeholder_image_url,
)


keycloak_service = create_keycloak_service(
    config,
    siteflow_registry,
    REGION,
    neon_database_url,
)

python_backend_service = gcp.cloudrunv2.Service(
    "python-backend",
    location=REGION,
    template=gcp.cloudrunv2.ServiceTemplateArgs(
        timeout="1200s",
        containers=[
            gcp.cloudrunv2.ServiceTemplateContainerArgs(
                image=placeholder_docker_image,
                envs=[
                    gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
                        name="DATABASE_URL", value=neon_database_url
                    ),
                    gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
                        name="KEYCLOAK_URL", value=keycloak_service.uri
                    ),
                ],
                resources=gcp.cloudrunv2.ServiceTemplateContainerResourcesArgs(
                    limits={"cpu": "2", "memory": "4Gi"}
                ),
            )
        ],
    ),
)

gcp.cloudrunv2.ServiceIamBinding(
    "backend-public-access",
    project=python_backend_service.project,
    location=python_backend_service.location,
    name=python_backend_service.name,
    role="roles/run.invoker",
    members=["allUsers"],
)

pulumi.export("gcp_backend_url", python_backend_service.uri)
pulumi.export("artifact_registry_url", siteflow_registry.name)
