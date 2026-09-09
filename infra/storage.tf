resource "aws_s3_bucket" "project" {

  for_each = toset(["frontend", "artifacts"])
  bucket   = "${local.name}-${data.aws_caller_identity.current.account_id}-${each.key}"
  lifecycle {
    prevent_destroy = true
  }


}

resource "aws_s3_bucket_public_access_block" "project" {

  for_each                = aws_s3_bucket.project
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true

}

resource "aws_s3_bucket_server_side_encryption_configuration" "project" {

  for_each = aws_s3_bucket.project
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }

  }


}

resource "aws_s3_bucket_versioning" "project" {

  for_each = aws_s3_bucket.project
  bucket   = each.value.id
  versioning_configuration {
    status = "Enabled"
  }


}

resource "aws_ecr_repository" "api" {

  name                 = local.name
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }


}

resource "aws_secretsmanager_secret" "runtime" {

  name                    = "${local.name}/runtime"
  description             = "Runtime credentials populated outside Terraform state"
  recovery_window_in_days = 7

}

resource "aws_cloudwatch_log_group" "api" {

  name              = "/f1/dev/api"
  retention_in_days = 14

}

resource "aws_cloudwatch_log_group" "build" {

  name              = "/f1/dev/build"
  retention_in_days = 14

}

