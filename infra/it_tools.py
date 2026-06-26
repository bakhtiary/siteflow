import pulumi
import pulumi_gcp as gcp
import pulumi_docker as docker



def create_it_tools_service(registry, region):
    it_tools_image_url = pulumi.Output.all(
        registry.location, registry.project, registry.repository_id
    ).apply(
        lambda args: f"{args[0]}-docker.pkg.dev/{args[1]}/{args[2]}/it-tools-custom:latest"
    )

    it_tools_image = docker.Image(
        "it-tools-custom-image",
        build=docker.DockerBuildArgs(
            context="./it-tools",
            dockerfile="./it-tools/Dockerfile",
            platform="linux/amd64",
        ),
        image_name=it_tools_image_url,
    )

    it_tools_service = gcp.cloudrunv2.Service(
        "it-tools",
        location=region,
        template=gcp.cloudrunv2.ServiceTemplateArgs(
            scaling=gcp.cloudrunv2.ServiceTemplateScalingArgs(max_instance_count=1),
            containers=[
                gcp.cloudrunv2.ServiceTemplateContainerArgs(
                    image=it_tools_image.image_name,
                    ports=gcp.cloudrunv2.ServiceTemplateContainerPortsArgs(
                        container_port=80
                    ),
                    resources=gcp.cloudrunv2.ServiceTemplateContainerResourcesArgs(
                        limits={"cpu": "2", "memory": "2Gi"}
                    ),
                )
            ],
        ),
    )

    gcp.cloudrunv2.ServiceIamBinding(
        "it-tools-public-access",
        project=it_tools_service.project,
        location=it_tools_service.location,
        name=it_tools_service.name,
        role="roles/run.invoker",
        members=["allUsers"],
    )


    pulumi.export("it_tools_url", it_tools_service.uri)