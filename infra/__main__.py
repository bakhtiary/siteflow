
import pulumi
import pulumi_gcp as gcp

from backend import create_backend_service
from create_placeholder_docker_image import create_placeholder_docker_image
from github_actions import create_github_actions_identity
from keycloak import create_keycloak_service

config = pulumi.Config()

neon_database_url = config.require_secret("neonDatabaseUrl")

REGION = "europe-west3"

create_github_actions_identity(config)

siteflow_registry = gcp.artifactregistry.Repository(
    "siteflow-registry",
    repository_id="siteflow",
    description="siteflow platform images",
    format="DOCKER",
    location=REGION,
)

website_info_bucket = gcp.storage.Bucket(
    "siteflow-website-info",
    name="siteflow-website-info",
    location=REGION.upper(),
    uniform_bucket_level_access=True,
    public_access_prevention="enforced",
)

pulumi_state_bucket = gcp.storage.Bucket(
    "siteflow-pulumi-state",
    name="siteflow-pulumi-state",
    location=REGION.upper(),
    uniform_bucket_level_access=True,
    public_access_prevention="enforced",
)

keycloak_service = create_keycloak_service(
    config,
    siteflow_registry,
    REGION,
    neon_database_url,
)

backend_image_url = config.get("backendImageUrl")
if backend_image_url is None:
    placeholder_docker_image = create_placeholder_docker_image(siteflow_registry)
    backend_image_url = placeholder_docker_image.image_name

create_backend_service(
    REGION,
    neon_database_url,
    keycloak_service.uri,
    backend_image_url,
)

pulumi.export("pulumi_state_bucket", pulumi_state_bucket.name)
pulumi.export("artifact_registry_url", siteflow_registry.name)
pulumi.export("website_info_bucket_name", website_info_bucket.name)
