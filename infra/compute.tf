locals {

  task_trust = jsonencode({
    Version = "2012-10-17", Statement = [{
      Effect = "Allow", Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }, Action = "sts:AssumeRole"
      }
    ]
    }
  )
  secret_keys = ["DATABASE_URL", "NL2SQL_DATABASE_URL", "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_PROJECT_ID", "OPENAI_MODEL", "CHAT_ACCESS_CODE"]

}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = local.task_trust

}

resource "aws_iam_role_policy_attachment" "execution" {

  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"

}

resource "aws_iam_role_policy" "secrets" {

  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17", Statement = [{
      Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_secretsmanager_secret.runtime.arn
      }
    ]
    }
  )

}

resource "aws_iam_role" "app" {
  name               = "${local.name}-app"
  assume_role_policy = local.task_trust

}

resource "aws_iam_role" "bootstrap" {
  name               = "${local.name}-bootstrap"
  assume_role_policy = local.task_trust

}

resource "aws_iam_role_policy" "bootstrap" {

  role = aws_iam_role.bootstrap.id
  policy = jsonencode({
    Version = "2012-10-17", Statement = [
      {
        Effect = "Allow", Action = ["s3:GetObject"], Resource = "${aws_s3_bucket.project["artifacts"].arn}/dataset/source.zip"
      },
      {
        Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = [aws_db_instance.project.master_user_secret[0].secret_arn, aws_secretsmanager_secret.runtime.arn]
      },
      {
        Effect = "Allow", Action = ["secretsmanager:PutSecretValue"], Resource = aws_secretsmanager_secret.runtime.arn
      }

    ]
    }
  )

}

resource "aws_ecs_cluster" "project" {
  name = local.name
}

resource "aws_ecs_task_definition" "api" {

  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.app.arn
  container_definitions = jsonencode([{
    name = "api", image = "${aws_ecr_repository.api.repository_url}:${var.image_tag}", essential = true,
    portMappings = [{
      containerPort = 8000, protocol = "tcp"
      }
    ],
    secrets = [for key in local.secret_keys : {
      name = key, valueFrom = "${aws_secretsmanager_secret.runtime.arn}:${key}::"
      }
    ],
    environment = [{
      name = "AWS_REGION", value = "eu-north-1"
      }
    ],
    logConfiguration = {
      logDriver = "awslogs", options = {
        awslogs-group = aws_cloudwatch_log_group.api.name, awslogs-region = "eu-north-1", awslogs-stream-prefix = "api"
      }

    }


    }
  ])

}

resource "aws_ecs_task_definition" "bootstrap" {

  family                   = "${local.name}-bootstrap"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.bootstrap.arn
  container_definitions = jsonencode([{
    name    = "bootstrap", image = "${aws_ecr_repository.api.repository_url}:${var.image_tag}", essential = true,
    command = ["python", "-m", "scripts.bootstrap_aws"],
    environment = [
      {
        name = "AWS_REGION", value = "eu-north-1"
      },
      {
        name = "F1_ACCOUNT_ID", value = "148356747273"
      },
      {
        name = "F1_ARTIFACT_BUCKET", value = aws_s3_bucket.project["artifacts"].id
      },
      {
        name = "F1_ADMIN_SECRET", value = aws_db_instance.project.master_user_secret[0].secret_arn
      },
      {
        name = "F1_RUNTIME_SECRET", value = aws_secretsmanager_secret.runtime.arn
      },
      {
        name = "F1_DB_HOST", value = aws_db_instance.project.address
      }

    ],
    logConfiguration = {
      logDriver = "awslogs", options = {
        awslogs-group = aws_cloudwatch_log_group.api.name, awslogs-region = "eu-north-1", awslogs-stream-prefix = "bootstrap"
      }

    }


    }
  ])

}

resource "aws_lb" "api" {

  name                       = "f1-strategist-dev"
  internal                   = true
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.alb.id]
  subnets                    = aws_subnet.private[*].id
  drop_invalid_header_fields = true

}

resource "aws_lb_target_group" "api" {

  name        = "f1-strategist-dev"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.project.id
  health_check {
    path              = "/api/health"
    matcher           = "200"
    interval          = 30
    timeout           = 10
    healthy_threshold = 2

  }


}

resource "aws_lb_listener" "api" {

  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn

  }


}

resource "aws_ecs_service" "api" {

  name                              = local.name
  cluster                           = aws_ecs_cluster.project.id
  task_definition                   = aws_ecs_task_definition.api.arn
  desired_count                     = var.desired_count
  launch_type                       = "FARGATE"
  health_check_grace_period_seconds = 120
  deployment_circuit_breaker {
    enable   = true
    rollback = true

  }

  network_configuration {

    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true

  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000

  }

  depends_on = [aws_lb_listener.api]

}

