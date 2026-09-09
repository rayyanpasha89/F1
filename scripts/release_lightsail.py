"""Guarded release and log export for the authorized F1 Lightsail alternative."""

import argparse
import json
import subprocess
from datetime import datetime, timezone

from backend.database import ROOT
from scripts.release_aws import guarded_session, outputs

SERVICE = "f1-strategist-demo"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["deploy", "logs"])
    parser.add_argument("--terraform", default="terraform")
    args = parser.parse_args()
    session = guarded_session()
    lightsail = session.client("lightsail")
    if args.stage == "deploy":
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
            raise RuntimeError("Commit and verify release files first")
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        session.client("ecr").describe_images(
            repositoryName="f1-race-strategist-dev", imageIds=[{"imageTag": sha}]
        )
        o = outputs(args.terraform)
        runtime = json.loads(
            session.client("secretsmanager").get_secret_value(SecretId=o["runtime_secret_arn"])[
                "SecretString"
            ]
        )
        runtime["F1_REQUIRE_READONLY"] = "1"
        lightsail.create_container_service_deployment(
            serviceName=SERVICE,
            containers={
                "web": {
                    "image": f"148356747273.dkr.ecr.eu-north-1.amazonaws.com/f1-race-strategist-dev:{sha}",
                    "environment": runtime,
                    "ports": {"8000": "HTTP"},
                }
            },
            publicEndpoint={
                "containerName": "web",
                "containerPort": 8000,
                "healthCheck": {
                    "healthyThreshold": 2,
                    "unhealthyThreshold": 3,
                    "timeoutSeconds": 10,
                    "intervalSeconds": 30,
                    "path": "/api/health",
                    "successCodes": "200",
                },
            },
        )
        print(json.dumps({"stage": "deployment_submitted", "commit": sha, "service": SERVICE}))
    else:
        # Explicit operator snapshot; Lightsail remains the continuous runtime log source.
        events = lightsail.get_container_log(serviceName=SERVICE, containerName="web")["logEvents"]
        log = session.client("logs")
        stream = "lightsail/" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        log.create_log_stream(logGroupName="/f1/dev/api", logStreamName=stream)
        if events:
            log.put_log_events(
                logGroupName="/f1/dev/api",
                logStreamName=stream,
                logEvents=sorted(
                    [
                        {
                            "timestamp": int(e["createdAt"].timestamp() * 1000),
                            "message": e["message"],
                        }
                        for e in events
                    ],
                    key=lambda e: e["timestamp"],
                ),
            )
        print(json.dumps({"stage": "logs_exported", "events": len(events), "stream": stream}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"stage": "failed", "error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1) from None
