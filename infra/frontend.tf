resource "aws_cloudfront_origin_access_control" "frontend" {

  name                              = local.name
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"

}

resource "aws_cloudfront_vpc_origin" "api" {

  vpc_origin_endpoint_config {

    name                   = local.name
    arn                    = aws_lb.api.arn
    http_port              = 80
    https_port             = 443
    origin_protocol_policy = "http-only"
    origin_ssl_protocols {
      items    = ["TLSv1.2"]
      quantity = 1

    }


  }

  depends_on = [aws_internet_gateway.project, aws_vpc_security_group_ingress_rule.cloudfront]

}

resource "aws_cloudfront_function" "spa" {

  name    = "${local.name}-spa"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = "function handler(event) { var r = event.request; if (r.uri.indexOf('/api/') !== 0 && r.uri.split('/').pop().indexOf('.') === -1) r.uri = '/index.html'; return r; }"

}

resource "aws_cloudfront_distribution" "app" {

  enabled             = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  origin {

    origin_id                = "frontend"
    domain_name              = aws_s3_bucket.project["frontend"].bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id

  }

  origin {

    origin_id   = "api"
    domain_name = aws_lb.api.dns_name
    vpc_origin_config {
      vpc_origin_id       = aws_cloudfront_vpc_origin.api.id
      origin_read_timeout = 60

    }


  }

  default_cache_behavior {

    target_origin_id       = "frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = "658327ea-f89d-4fab-a63d-7e88639e58f6"
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa.arn

    }


  }

  ordered_cache_behavior {

    path_pattern             = "/api/*"
    target_origin_id         = "api"
    viewer_protocol_policy   = "https-only"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = "413f1604-2b3e-4bd4-aaa7-832ab7f7d5bf"
    origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac"

  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }

  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }


}

resource "aws_s3_bucket_policy" "frontend" {

  bucket = aws_s3_bucket.project["frontend"].id
  policy = jsonencode({
    Version = "2012-10-17", Statement = [{
      Effect = "Allow", Principal = {
        Service = "cloudfront.amazonaws.com"
        }, Action = "s3:GetObject", Resource = "${aws_s3_bucket.project["frontend"].arn}/*", Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.app.arn
        }

      }

      }
    ]
    }
  )

}

