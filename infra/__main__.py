import pulumi
import pulumi_cloudflare as cloudflare
import pulumi_docker as docker
import pulumi_gcp as gcp

# Initialize Pulumi Configuration
config = pulumi.Config()

# Secrets and structural configuration variables
neon_database_url = config.require_secret("neonDatabaseUrl")
keycloak_admin_user = config.get("keycloakAdminUser") or "admin"
keycloak_admin_password = config.require_secret("keycloakAdminPassword")
cloudflare_account_id = config.require("cloudflareAccountId")

# EUROPEAN LOCATION DEFINITIONS
# Using europe-west3 (Frankfurt, Germany) as the primary hub
EUROPE_REGION = "europe-west3"

# 1. CREATE GOOGLE ARTIFACT REGISTRY IN EUROPE
siteflow_registry = gcp.artifactregistry.Repository(
    "siteflow-registry",
    repository_id="siteflow",
    description="European Docker repository for siteflow platform images",
    format="DOCKER",
    location=EUROPE_REGION, # Placed in Frankfurt
)

# 2. AUTOMATICALLY BUILD AND PUSH THE KEYCLOAK DOCKER IMAGE
# Constructs the target URL using the European domain: europe-west3-docker.pkg.dev
keycloak_image_url = pulumi.Output.all(
    siteflow_registry.location, siteflow_registry.project, siteflow_registry.repository_id
).apply(
    lambda args: f"{args[0]}-docker.pkg.dev/{args[1]}/{args[2]}/keycloak-custom:latest"
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

# 3. PROVISION KEYCLOAK AUTHENTICATION SERVICE (GCP Cloud Run in Europe)
keycloak_service = gcp.cloudrunv2.Service(
    "keycloak-auth",
    location=EUROPE_REGION, # Placed in Frankfurt
    template=gcp.cloudrunv2.ServiceTemplateArgs(
        scaling=gcp.cloudrunv2.ServiceTemplateScalingArgs(max_instance_count=5),
        containers=[
            gcp.cloudrunv2.ServiceTemplateContainerArgs(
                image=keycloak_docker_image.image_name,
                args=["start", "--optimized"],
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
                ports=[
                    gcp.cloudrunv2.ServiceTemplateContainerPortArgs(container_port=8080)
                ],
                resources=gcp.cloudrunv2.ServiceTemplateContainerResourcesArgs(
                    limits={"cpu": "2", "memory": "2Gi"}
                ),
            )
        ],
    ),
)

# Give Keycloak public web access permissions
gcp.cloudrunv2.ServiceIamBinding(
    "keycloak-public-access",
    project=keycloak_service.project,
    location=keycloak_service.location,
    name=keycloak_service.name,
    role="roles/run.viewer",
    members=["allUsers"],
)

# 4. PROVISION THE PYTHON BACKEND SERVICE (GCP Cloud Run in Europe)
python_backend_service = gcp.cloudrunv2.Service(
    "python-backend",
    location=EUROPE_REGION, # Placed in Frankfurt
    template=gcp.cloudrunv2.ServiceTemplateArgs(
        timeout="1200s", # Retains 20-minute execution window for website generation tasks
        containers=[
            gcp.cloudrunv2.ServiceTemplateContainerArgs(
                image="gcr.io/your-gcp-project-id/python-backend:latest", # Can be changed to use the siteflow registry asset as well
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
    role="roles/run.viewer",
    members=["allUsers"],
)

# 5. PROVISION THE FRONTEND SYSTEM (Cloudflare Pages - Globally optimized, heavily cached in Europe)
frontend_app = cloudflare.PagesProject(
    "frontend-ui",
    account_id=cloudflare_account_id,
    name="saas-website-builder-frontend",
    source=cloudflare.PagesProjectSourceArgs(
        type="github",
        config=cloudflare.PagesProjectSourceConfigArgs(
            owner="your-github-username",
            repo_name="your-frontend-repo",
            production_branch="main",
        ),
    ),
    deployment_configs=cloudflare.PagesProjectDeploymentConfigsArgs(
        production=cloudflare.PagesProjectDeploymentConfigsProductionArgs(
            environment_variables={
                "NEXT_PUBLIC_BACKEND_API_URL": python_backend_service.uri,
                "NEXT_PUBLIC_KEYCLOAK_AUTH_URL": keycloak_service.uri,
            }
        )
    ),
)

# EXPORT RE-LOCATED ENDPOINTS
pulumi.export("cloudflare_frontend_url", frontend_app.subdomain)
pulumi.export("gcp_backend_url", python_backend_service.uri)
pulumi.export("gcp_keycloak_url", keycloak_service.uri)
pulumi.export("european_artifact_registry_url", siteflow_registry.name)
