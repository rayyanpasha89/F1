# AWS deployment

## Active Lightsail deployment

The dev application is reachable at https://f1-strategist-demo.ys85rp5g9ncdj.eu-north-1.cs.amazonlightsail.com/ . Initial public smoke checks passed for frontend, deep links, health, seasons, standings, qualifying, profiles and all 20 Monaco podium probabilities. Subsequent product improvements require their own build and verification; see the worklog for the released commit.

The user authorized Lightsail after CloudFront required account verification and RDS rejected seven-day backup retention on the account plan. Terraform under `infra/lightsail/` manages the small container service, its narrowly scoped ECR pull policy, and an encrypted PostgreSQL 16 database through a CloudFormation resource. Database deletion/replacement is retained. This account is 148356747273, CLI default profile, region eu-north-1. Never use the Naaz configuration.

React and FastAPI share one HTTPS origin. The database remains private; a real container TCP probe succeeded without public database mode. Strict ingestion loaded 701,433 rows and verified all 14 counts. The bootstrap container uses a short-lived presigned source URL and a temporary master credential, then the master password is rotated. Application containers receive only SELECT-only database credentials, with TLS `verify-full`. Production startup independently rejects writable credentials.

Lightsail does not accept ECS secret references or task roles. The operator retrieves the F1 runtime secret from Secrets Manager and passes approved values as Lightsail environment variables. Principals allowed to inspect deployment configuration can view those values; limit that access. No long-lived AWS access keys are placed in containers. The bootstrap deployment's now-rotated master credential remains in deployment history; preserve this distinction when reviewing security.

## Build and release

From the repository root, with a clean tested commit and locally generated trusted model artifacts:

```sh
python -m scripts.release_aws build --terraform /absolute/path/to/terraform
# Wait for the reported CodeBuild ID to succeed.
python -m scripts.release_lightsail deploy --terraform /absolute/path/to/terraform
```

Both stages explicitly check STS and the default profile before AWS mutations. ECR image tags are Git commit SHAs. Never archive `.env` or Terraform state. `scripts/bootstrap_lightsail.py` is the one-off ingestion routine, invoked inside the private service with the bootstrap URL, reader password and presigned source URL supplied through environment. It verifies CSV hashes and refuses to repair a nonempty inconsistent database. Do not rerun ingestion against unrelated data.

For rollback, deploy a previously verified existing image through the Lightsail API after the same account checks; do not restore or delete the database as an application rollback. Terraform creation and application image releases are separate operations. Production environment includes `DATABASE_URL`, `SQL_READONLY_DATABASE_URL`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_PROJECT_ID`, `OPENAI_MODEL`, `CHAT_ACCESS_CODE` and `F1_REQUIRE_READONLY=1`.

## Logging and costs

Lightsail retains continuous container stdout/stderr. CodeBuild writes to CloudWatch `/f1/dev/build`. Export an operator snapshot of the web container logs into `/f1/dev/api` with:

```sh
python -m scripts.release_lightsail logs
```

This is a bounded snapshot of the first returned log page, not automatic continuous CloudWatch forwarding. CloudWatch retention is 14 days. Do not place access codes in URLs or logs. Chat budgets are per-process and reset after restart, so they are not a durable billing cap.

The small container service is approximately $15/month and the micro PostgreSQL bundle approximately $15/month, plus Bedrock and incidental storage/logging. Previously created ALB and supporting resources still incur charges; no destructive cleanup was authorized. The original architecture and its retained resources are documented below for traceability. Do not apply or destroy that stack casually.

## Original architecture, partially provisioned

# AWS development deployment

Infrastructure is in `infra/`. Deployment is not yet verified. See worklog for actual execution status.

Only account **148356747273**, profile **default**, region **eu-north-1** are allowed. Before each mutation stage:

```sh
aws sts get-caller-identity --profile default
aws configure list --profile default
```

If identity differs, stop. Never select the Naaz profile. Terraform also enforces the account allowlist.

## Prerequisites and plan

Terraform 1.13+, AWS CLI, Python 3.11 environment, Git, npm, audited source CSV package, trained local model artifacts, and configured Bedrock credentials in ignored `.env`. Read ADR 005 for architecture/security tradeoffs. No local Docker engine is available; CodeBuild provides the Linux container build and verification gate.

```sh
terraform -chdir=infra init
terraform -chdir=infra validate
terraform -chdir=infra plan -out=initial.tfplan
terraform -chdir=infra show initial.tfplan
# Only after reviewing resources, identity and costs:
terraform -chdir=infra apply initial.tfplan
```

Initial desired count is zero because image and database initialization must succeed before traffic. RDS and load balancer still incur charges at zero tasks. No destroy operation is authorized. RDS and source buckets have Terraform destruction protection; RDS additionally requires a final snapshot.

## Cost assessment before first deployment

Initial plan: **49 additions, no changes, no deletions**. Dedicated VPC/four subnets/security groups/IGW, two private S3 buckets, CloudFront and VPC origin, internal ALB, RDS, ECS cluster/service/two task definitions, ECR, Secrets Manager, CodeBuild, scoped IAM, two log groups and an alarm.

Budget approximately **USD 55–75/month** for continuous low-traffic dev operation, excluding tax and substantial Bedrock/traffic/build usage; this is an estimate, not a spending cap. Pricing API checked 2026-09-09: Stockholm RDS t4g.micro $0.016/hour (~$11.68/730h); ALB $0.02394/hour (~$17.48) plus $0.0076/LCU-hour. Fargate CPU/memory roughly $18–23/month, task public IPv4 roughly $3.65/month, RDS 20-GB storage and small Secrets Manager/log/S3/ECR usage add several dollars. Backups beyond included allowance, storage autoscaling to 30 GB, deployment overlap and logs can add cost. CodeBuild and Bedrock charge on use. There is no NAT gateway. Persistent billable resources: RDS, database storage/backups, ALB, running task/IPv4, retained artifacts/logs/secrets.

Pricing references: https://aws.amazon.com/fargate/pricing/ and https://aws.amazon.com/rds/postgresql/pricing/ and https://aws.amazon.com/elasticloadbalancing/pricing/ . Rates vary; inspect billing after deployment. Stopping ECS alone does not stop RDS/ALB charges.

## Release and database workflow

Build input must be a clean committed Git archive with only trusted `models/*.joblib` added. Never package `.env`, state or raw CSVs into the image. Upload the separately audited source ZIP privately. Populate runtime secret from `.env` through the SDK without printing values, including a random `CHAT_ACCESS_CODE`. CodeBuild pushes the Git-SHA tag only after model import succeeds. Update Terraform image_tag, keeping desired_count=0; run bootstrap task and inspect its exit status/counts before setting desired_count=1. Bootstrap never drops tables; a populated database with wrong counts stops for investigation.

Both DATABASE_URL and SQL_READONLY_DATABASE_URL must use the SELECT-only reader and `sslmode=verify-full` with the RDS CA bundle. OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_PROJECT_ID and OPENAI_MODEL are ECS secret references. Region is explicit. Upload frontend production assets, invalidate CloudFront, then verify health, analytics, predictions, statistics with visible SQL and unsupported refusal.

## Rollback and operations

Reapply a previously verified immutable image tag and deploy the matching frontend Git build. Do not restore/delete the database as an application rollback. Inspect `/f1/dev/api` and `/f1/dev/build` in CloudWatch; application errors omit credentials. The unhealthy-target alarm is visible in CloudWatch but has no notification destination. Keep protected copies of local Terraform state. Obtain explicit user authorization before any destructive cleanup. This dev environment has no automatic release workflow or durable chat billing quota.
