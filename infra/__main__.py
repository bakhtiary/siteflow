
import pulumi
import pulumi_gcp as gcp

from backend import create_backend_service
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
    "website-info-bucket",
    name="siteflow-website-info",
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

create_backend_service(
    siteflow_registry,
    REGION,
    neon_database_url,
    keycloak_service.uri,
)
pulumi.export("artifact_registry_url", siteflow_registry.name)
pulumi.export("website_info_bucket_name", website_info_bucket.name)
