import pulumi
import pulumi_gcp as gcp


def create_backend_service(
    region: str,
    database_url: pulumi.Output[str],
    keycloak_url: pulumi.Output[str],
    image_url: pulumi.Input[str],
) -> gcp.cloudrunv2.Service:
    backend_service = gcp.cloudrunv2.Service(
        "python-backend",
        location=region,
        template=gcp.cloudrunv2.ServiceTemplateArgs(
            timeout="1200s",
            containers=[
                gcp.cloudrunv2.ServiceTemplateContainerArgs(
                    image=image_url,
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
                    ports=gcp.cloudrunv2.ServiceTemplateContainerPortsArgs(
                        container_port=8000
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
