from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import pulumi
import pulumi_docker as docker
import pulumi_gcp as gcp

# Initialize Pulumi Configuration
config = pulumi.Config()

neon_database_url = config.require_secret("neonDatabaseUrl")
keycloak_admin_user = config.get("keycloakAdminUser") or "admin"
keycloak_admin_password = config.require_secret("keycloakAdminPassword")

REGION = "europe-west3"

siteflow_registry = gcp.artifactregistry.Repository(
    "siteflow-registry",
    repository_id="siteflow",
    description="siteflow platform images",
    format="DOCKER",
    location=REGION,
)

keycloak_image_url = pulumi.Output.all(
    siteflow_registry.location, siteflow_registry.project, siteflow_registry.repository_id
).apply(
    lambda args: f"{args[0]}-docker.pkg.dev/{args[1]}/{args[2]}/keycloak-custom:latest"
)

placeholder_image_url = pulumi.Output.all(
    siteflow_registry.location, siteflow_registry.project, siteflow_registry.repository_id
).apply(
    lambda args: f"{args[0]}-docker.pkg.dev/{args[1]}/{args[2]}/siteflow-placeholder:latest"
)


keycloak_docker_image = docker.Image(
    "keycloak-custom-image",
    build=docker.DockerBuildArgs(
        context="./keycloak",
        dockerfile="./keycloak/Dockerfile",
        platform="linux/amd64",
    ),
    image_name=keycloak_image_url,
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


def _postgres_url_to_jdbc(url: str) -> str:
    if url.startswith("jdbc:postgresql://"):
        return url

    parsed = urlsplit(url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        return url

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))

    if parsed.username:
        query.setdefault("user", parsed.username)
    if parsed.password:
        query.setdefault("password", parsed.password)

    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"

    netloc = hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"

    jdbc_url = urlunsplit(
        (
            "jdbc:postgresql",
            netloc,
            parsed.path,
            urlencode(query, quote_via=quote),
            "",
        )
    )
    return jdbc_url

keycloak_service = gcp.cloudrunv2.Service(
    "keycloak-auth",
    location=REGION, # Placed in Frankfurt
    template=gcp.cloudrunv2.ServiceTemplateArgs(
        scaling=gcp.cloudrunv2.ServiceTemplateScalingArgs(max_instance_count=5),
        containers=[
            gcp.cloudrunv2.ServiceTemplateContainerArgs(
                image=keycloak_docker_image.image_name,
                args=["start", "--optimized", "--hostname-strict", "false"],
                envs=[
                    gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
                        name="KEYCLOAK_ADMIN", value=keycloak_admin_user
                    ),
                    gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
                        name="KEYCLOAK_ADMIN_PASSWORD", value=keycloak_admin_password,
                    ),
                    gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
                        name="KC_DB", value="postgres"
                    ),
                    gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
                        name="KC_DB_URL", value=neon_database_url
                    ),
                    gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
                        name="KC_PROXY", value="edge"
                    ),
                    gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
                        name="KC_HTTP_ENABLED", value="true"
                    ),
                ],
                ports=gcp.cloudrunv2.ServiceTemplateContainerPortsArgs(container_port=8080),
                resources=gcp.cloudrunv2.ServiceTemplateContainerResourcesArgs(
                    limits={"cpu": "2", "memory": "2Gi"}
                ),
            )
        ],
    ),
)

gcp.cloudrunv2.ServiceIamBinding(
    "keycloak-public-access",
    project=keycloak_service.project,
    location=keycloak_service.location,
    name=keycloak_service.name,
    role="roles/run.viewer",
    members=["allUsers"],
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
                        name="DATABASE_URL", value=neon_database_url.apply(_postgres_url_to_jdbc)
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
    role="roles/run.viewer",
    members=["allUsers"],
)

pulumi.export("gcp_backend_url", python_backend_service.uri)
pulumi.export("gcp_keycloak_url", keycloak_service.uri)
pulumi.export("artifact_registry_url", siteflow_registry.name)
