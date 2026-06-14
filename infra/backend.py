import pulumi
import pulumi_docker as docker
import pulumi_gcp as gcp


def create_backend_service(
    registry: gcp.artifactregistry.Repository,
    region: str,
    database_url: pulumi.Output[str],
    keycloak_url: pulumi.Output[str],
) -> gcp.cloudrunv2.Service:
    placeholder_image_url = pulumi.Output.all(
        registry.location, registry.project, registry.repository_id
    ).apply(
        lambda args: (
            f"{args[0]}-docker.pkg.dev/{args[1]}/{args[2]}/"
            "siteflow-placeholder:latest"
        )
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

    backend_service = gcp.cloudrunv2.Service(
        "python-backend",
        location=region,
        template=gcp.cloudrunv2.ServiceTemplateArgs(
            timeout="1200s",
            containers=[
                gcp.cloudrunv2.ServiceTemplateContainerArgs(
                    image=placeholder_docker_image.image_name,
                    envs=[
                        gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
                            name="DATABASE_URL", value=database_url
                        ),
                        gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
                            name="KEYCLOAK_URL", value=keycloak_url
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
        project=backend_service.project,
        location=backend_service.location,
        name=backend_service.name,
        role="roles/run.invoker",
        members=["allUsers"],
    )

    pulumi.export("gcp_backend_url", backend_service.uri)

    return backend_service
