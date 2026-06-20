from dataclasses import dataclass

import pulumi
import pulumi_gcp as gcp


@dataclass(frozen=True)
class GithubActionsIdentity:
    service_account: gcp.serviceaccount.Account
    workload_identity_pool: gcp.iam.WorkloadIdentityPool
    workload_identity_provider: gcp.iam.WorkloadIdentityPoolProvider


def create_github_actions_identity(
    config: pulumi.Config,
) -> GithubActionsIdentity:
    project = pulumi.Config("gcp").require("project")
    github_repository = config.require("githubRepository")

    iam_credentials_api = gcp.projects.Service(
        "iam-credentials-api",
        project=project,
        service="iamcredentials.googleapis.com",
        disable_on_destroy=False,
    )

    service_account = gcp.serviceaccount.Account(
        "github-actions-deployer",
        account_id="github-actions",
        display_name="GitHub Actions deployer",
        description="Service account impersonated by GitHub Actions via Workload Identity Federation.",
        project=project,
        opts=pulumi.ResourceOptions(depends_on=[iam_credentials_api]),
    )

    pool = gcp.iam.WorkloadIdentityPool(
        "github-pool",
        workload_identity_pool_id="github-pool",
        display_name="GitHub Actions Pool",
        description="Workload Identity Pool for GitHub Actions.",
        project=project,
        opts=pulumi.ResourceOptions(depends_on=[iam_credentials_api]),
    )

    provider = gcp.iam.WorkloadIdentityPoolProvider(
        "github-provider",
        workload_identity_pool_id=pool.workload_identity_pool_id,
        workload_identity_pool_provider_id="github-provider",
        display_name="GitHub provider",
        attribute_mapping={
            "google.subject": "assertion.sub",
            "attribute.repository": "assertion.repository",
        },
        attribute_condition=f'assertion.repository == "{github_repository}"',
        oidc=gcp.iam.WorkloadIdentityPoolProviderOidcArgs(
            issuer_uri="https://token.actions.githubusercontent.com",
        ),
        project=project,
    )

    project_info = gcp.organizations.get_project_output(project_id=project)
    github_principal = project_info.number.apply(
        lambda project_number: (
            "principalSet://iam.googleapis.com/"
            f"projects/{project_number}/locations/global/"
            "workloadIdentityPools/github-pool/"
            f"attribute.repository/{github_repository}"
        )
    )

    gcp.serviceaccount.IAMMember(
        "github-actions-workload-identity-user",
        service_account_id=service_account.name,
        role="roles/iam.workloadIdentityUser",
        member=github_principal,
    )

    deployer_member = service_account.email.apply(lambda email: f"serviceAccount:{email}")
    for role in [
        "roles/artifactregistry.writer",
        "roles/iam.serviceAccountUser",
        "roles/run.admin",
    ]:
        resource_name = role.split("/")[-1].replace(".", "-").lower()
        gcp.projects.IAMMember(
            f"github-actions-{resource_name}",
            project=project,
            role=role,
            member=deployer_member,
        )

    gcp.storage.BucketIAMMember(
        "github-actions-pulumi-state-object-admin",
        bucket="siteflow-pulumi-state",
        role="roles/storage.objectAdmin",
        member=deployer_member,
    )

    pulumi.export("github_actions_service_account_email", service_account.email)
    pulumi.export("github_actions_workload_identity_provider", provider.name)

    return GithubActionsIdentity(
        service_account=service_account,
        workload_identity_pool=pool,
        workload_identity_provider=provider,
    )
