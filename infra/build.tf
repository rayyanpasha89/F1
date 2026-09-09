resource "aws_iam_role" "build" {

  name = "${local.name}-build"
  assume_role_policy = jsonencode({
    Version = "2012-10-17", Statement = [{
      Effect = "Allow", Principal = {
        Service = "codebuild.amazonaws.com"
      }, Action = "sts:AssumeRole"
      }
    ]
    }
  )

}

resource "aws_iam_role_policy" "build" {

  role = aws_iam_role.build.id
  policy = jsonencode({
    Version = "2012-10-17", Statement = [
      {
        Effect = "Allow", Action = ["s3:GetObject", "s3:GetObjectVersion"], Resource = "${aws_s3_bucket.project["artifacts"].arn}/build/*"
      },
      {
        Effect = "Allow", Action = ["s3:GetBucketLocation"], Resource = aws_s3_bucket.project["artifacts"].arn
      },
      {
        Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*"
      },
      {
        Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:CompleteLayerUpload", "ecr:InitiateLayerUpload", "ecr:PutImage", "ecr:UploadLayerPart", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"], Resource = aws_ecr_repository.api.arn
      },
      {
        Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.build.arn}:*"
      }

    ]
    }
  )

}

resource "aws_codebuild_project" "api" {

  name          = local.name
  service_role  = aws_iam_role.build.arn
  build_timeout = 20
  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {

    compute_type    = "BUILD_GENERAL1_SMALL"
    image           = "aws/codebuild/standard:7.0"
    type            = "LINUX_CONTAINER"
    privileged_mode = true
    environment_variable {
      name  = "ECR_URL"
      value = aws_ecr_repository.api.repository_url

    }


  }

  source {
    type      = "S3"
    location  = "${aws_s3_bucket.project["artifacts"].id}/build/source.zip"
    buildspec = "buildspec.yml"

  }

  logs_config {
    cloudwatch_logs {
      group_name = aws_cloudwatch_log_group.build.name
    }

  }


}

resource "aws_cloudwatch_metric_alarm" "unhealthy" {

  alarm_name          = "${local.name}-unhealthy"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions = {
    LoadBalancer = aws_lb.api.arn_suffix, TargetGroup = aws_lb_target_group.api.arn_suffix
  }


}

