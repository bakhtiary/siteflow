import pulumi
import pulumi_docker as docker
import pulumi_gcp as gcp


def create_placeholder_docker_image(
    registry: gcp.artifactregistry.Repository,
) -> docker.Image:
    placeholder_image_url = pulumi.Output.all(
        registry.location, registry.project, registry.repository_id
    ).apply(
        lambda args: (
            f"{args[0]}-docker.pkg.dev/{args[1]}/{args[2]}/"
            "siteflow-placeholder:latest"
        )
    )

    return docker.Image(
        "placeholder-custom-image",
        build=docker.DockerBuildArgs(
            context="./placeholderService",
            dockerfile="./placeholderService/Dockerfile",
            platform="linux/amd64",
        ),
        image_name=placeholder_image_url,
    )
