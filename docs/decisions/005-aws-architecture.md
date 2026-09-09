# ADR 005: isolated AWS development deployment

Date: 2026-09-09. Status: planned, Terraform validated; deployment not yet verified.

Use only confirmed account 148356747273, explicit default profile and eu-north-1. Provider account allowlist prevents accidental use of the other account. No pre-existing application resources are imported or changed.

S3/CloudFront serves React over HTTPS. CloudFront VPC origin reaches an internal ALB, then a 0.5-vCPU/1-GiB Fargate task. The private origin hop uses HTTP inside the VPC; this is not end-to-end transport encryption. A public ALB with unencrypted internet transit was rejected. Custom-domain TLS would require a user-owned domain, which was not provided. Tasks have public IPv4 for outbound ECR/Bedrock access but accept inbound traffic only from the ALB security group. No NAT gateway. PostgreSQL 16 runs on private encrypted RDS t4g.micro with verified TLS, seven-day backups and deletion protection. Single task and Single-AZ RDS are appropriate for this academic dev environment, not a high-availability production guarantee.

A one-off task ingests hash-verified source into the new database and grants a SELECT-only runtime role. Administrator credentials use RDS-managed Secrets Manager storage. Runtime credentials are populated outside Terraform state. App task role has no AWS API permissions; bootstrap role is separately scoped. Secret rotation requires a new ECS deployment. An access code protects billable chat; per-process request limits are additional safeguards and reset on restart.

Docker is unavailable locally. AWS CodeBuild builds an exact Git archive plus trusted locally trained artifacts, verifies model deserialization in the Linux image and pushes an immutable Git-SHA ECR tag. This is the first container execution gate; no claim of prior local Docker verification is made. GitHub CI runs without cloud credentials. Infrastructure and releases are deliberately initiated by the operator with explicit identity checks. CloudWatch keeps application/build logs 14 days and records an unhealthy-target alarm. Alarm has no notification subscription yet.

Terraform state is local and ignored; preserve a protected backup. Never commit state, plans or credentials. Shared remote state/locking is deferred for a single-operator dev deployment, not represented as implemented.
