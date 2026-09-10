"""Explicit operator release stages. Local SDK calls always use default profile."""

import argparse
import hashlib
import io
import json
import os
import secrets
import subprocess
import zipfile
from pathlib import Path

import boto3
from dotenv import dotenv_values

from backend.database import ROOT, SCHEMA
from backend.ml.evidence import verify_model_bundle


def guarded_session():
    identity = json.loads(
        subprocess.check_output(
            ["aws", "sts", "get-caller-identity", "--profile", "default"], text=True
        )
    )
    subprocess.run(["aws", "configure", "list", "--profile", "default"], check=True)
    if identity["Account"] != "148356747273":
        raise RuntimeError("Wrong account; refusing AWS mutations")
    print(json.dumps({"account": identity["Account"], "arn": identity["Arn"]}), flush=True)
    return boto3.Session(profile_name="default", region_name="eu-north-1")


def outputs(terraform):
    data = json.loads(
        subprocess.check_output([terraform, "-chdir=infra", "output", "-json"], cwd=ROOT)
    )
    return {key: entry["value"] for key, entry in data.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prepare", "build", "bootstrap", "frontend"])
    parser.add_argument("--terraform", default="terraform")
    parser.add_argument("--access-code-file", type=Path)
    args = parser.parse_args()
    o = outputs(args.terraform)
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise RuntimeError("Commit and verify release files before deployment")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    session = guarded_session()
    s3 = session.client("s3")
    if args.stage == "prepare":
        if not args.access_code_file or args.access_code_file.exists():
            raise ValueError("Provide a new protected --access-code-file path")
        env = dotenv_values(ROOT / ".env")
        keys = ["OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_PROJECT_ID", "OPENAI_MODEL"]
        if not all(env.get(key) for key in keys):
            raise ValueError("Bedrock configuration is incomplete")
        sm = session.client("secretsmanager")
        # Initial provisioning only. Existing credentials are never silently replaced.
        try:
            sm.get_secret_value(SecretId=o["runtime_secret_arn"])
        except sm.exceptions.ResourceNotFoundException:
            pass
        else:
            raise RuntimeError(
                "Runtime secret already initialized; use an explicit rotation workflow"
            )
        runtime = {key: env[key] for key in keys}
        runtime["CHAT_ACCESS_CODE"] = secrets.token_urlsafe(24)
        args.access_code_file.parent.mkdir(parents=True, exist_ok=True)
        with os.fdopen(
            os.open(args.access_code_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
        ) as stream:
            stream.write(runtime["CHAT_ACCESS_CODE"] + "\n")
        sm.put_secret_value(SecretId=o["runtime_secret_arn"], SecretString=json.dumps(runtime))
        audit = json.loads((ROOT / "reports/data_audit.json").read_text())
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in SCHEMA:
                path = ROOT / "dataset" / f"{name}.csv"
                if hashlib.sha256(path.read_bytes()).hexdigest() != audit["tables"][name]["sha256"]:
                    raise ValueError("Dataset differs from audited source")
                archive.write(path, path.name)
        s3.put_object(
            Bucket=o["artifact_bucket"],
            Key="dataset/source.zip",
            Body=data.getvalue(),
            ServerSideEncryption="AES256",
        )
        print("Runtime secret initialized and audited source uploaded; secret values omitted.")
    elif args.stage == "build":
        verify_model_bundle(ROOT)
        source = subprocess.check_output(["git", "archive", "--format=zip", "HEAD"], cwd=ROOT)
        data = io.BytesIO(source)
        with zipfile.ZipFile(data, "a", zipfile.ZIP_DEFLATED) as archive:
            for name in ["grid_baseline.joblib", "podium_model.joblib"]:
                archive.write(ROOT / "models" / name, f"models/{name}")
        key = f"build/{sha}.zip"
        s3.put_object(
            Bucket=o["artifact_bucket"],
            Key=key,
            Body=data.getvalue(),
            ServerSideEncryption="AES256",
        )
        result = session.client("codebuild").start_build(
            projectName=o["build_project"],
            sourceLocationOverride=f"{o['artifact_bucket']}/{key}",
            environmentVariablesOverride=[{"name": "IMAGE_TAG", "value": sha, "type": "PLAINTEXT"}],
        )
        print(
            json.dumps(
                {
                    "build_id": result["build"]["id"],
                    "image_tag": sha,
                    "source_sha256": hashlib.sha256(data.getvalue()).hexdigest(),
                }
            )
        )
    elif args.stage == "bootstrap":
        result = session.client("ecs").run_task(
            cluster=o["cluster"],
            taskDefinition=o["bootstrap_task"],
            launchType="FARGATE",
            count=1,
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": o["task_subnets"],
                    "securityGroups": [o["task_security_group"]],
                    "assignPublicIp": "ENABLED",
                }
            },
        )
        if result["failures"]:
            raise RuntimeError("ECS rejected bootstrap task")
        print(json.dumps({"task_arn": result["tasks"][0]["taskArn"]}))
    else:
        # Build the actual checked-in frontend on every upload; stale dist is not accepted.
        subprocess.run(["npm", "run", "build", "--prefix", "frontend"], cwd=ROOT, check=True)
        import mimetypes

        for path in sorted((ROOT / "frontend/dist").rglob("*")):
            if path.is_file():
                key = str(path.relative_to(ROOT / "frontend/dist"))
                s3.upload_file(
                    str(path),
                    o["frontend_bucket"],
                    key,
                    ExtraArgs={
                        "ContentType": mimetypes.guess_type(key)[0] or "application/octet-stream",
                        "CacheControl": "no-cache"
                        if key == "index.html"
                        else "public,max-age=31536000,immutable",
                    },
                )
        result = session.client("cloudfront").create_invalidation(
            DistributionId=o["distribution_id"],
            InvalidationBatch={
                "Paths": {"Quantity": 1, "Items": ["/*"]},
                "CallerReference": f"{sha}-{secrets.token_hex(4)}",
            },
        )
        print(
            json.dumps(
                {"url": o["url"], "invalidation": result["Invalidation"]["Id"], "git_commit": sha}
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"stage": "failed", "error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1) from None
