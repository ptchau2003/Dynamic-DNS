terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
  }
}

provider "aws" {
  profile = "default"
  region  = var.region
}

resource "aws_route53_zone" "private" {
  name                        = var.private_hosted_zone_name
  force_destroy = true
  vpc {
    vpc_id = var.vpc_id
  }

}

resource "aws_dynamodb_table" "dynamoic_dns_table" {
  name           = "DDNS"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "hostname"

  attribute {
    name = "hostname"
    type = "S"
  }
  tags = {
    Name        = var.environment
  }
  depends_on = [aws_route53_zone.private]
}

output "DYNAMO_DB_TABLE" {
  value = aws_dynamodb_table.dynamoic_dns_table.arn
}

resource "aws_iam_role" "iam_for_lambda" {
  name = var.lambda_name
  assume_role_policy = <<EOF
{
        "Version": "2012-10-17",
        "Statement": [
          {
            "Action": "sts:AssumeRole",
            "Principal": {
              "Service": "lambda.amazonaws.com"
            },
            "Effect": "Allow",
            "Sid": ""
          }
        ]
} 
EOF

  inline_policy {
    name = var.lambda_name
    policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "ec2:Describe*",
    "Resource": "*"
  }, {
    "Effect": "Allow",
    "Action": [
      "dynamodb:*"
    ],
    "Resource": "*"
  }, {
    "Effect": "Allow",
    "Action": [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ],
    "Resource": "*"
  }, {
    "Effect": "Allow",
    "Action": [
      "route53:*"
    ],
    "Resource": [
      "*"
    ]
  }]
} 
EOF
  }
}

resource "aws_lambda_function" "dynamic_dns" {
  function_name = var.lambda_name
  publish        = "true"
  filename      = var.python_filename
  source_code_hash = filebase64sha256(var.python_filename)
  description    = var.python_filename
  handler = var.handler_name
  runtime = "python3.8"
  timeout = var.lambda_timeout
  memory_size = var.lambda_memory_size
  role = aws_iam_role.iam_for_lambda.arn
  environment {
    variables = {
      HOST_ZONE_NAME = var.private_hosted_zone_name
      HOSTZONE_ID = aws_route53_zone.private.zone_id
      RECORD_TYPE = var.record_type 
      DYNAMODB_TABLE = aws_dynamodb_table.dynamoic_dns_table.name
    }
  }
  depends_on = [aws_route53_zone.private,aws_iam_role.iam_for_lambda]
}

output "LAMBDA_FUNCTION_ARN" {
  value = aws_lambda_function.dynamic_dns.arn
}

resource "aws_cloudwatch_event_rule" "ec2_running_terminated" {
  name        = "ec2_running_terminated"
  description = "Calling DNS update Lambda when EC2 is running or being terminated"

  event_pattern = <<EOF
{
  "source": [
    "aws.ec2"
  ],
  "detail-type": [
    "EC2 Instance State-change Notification"
  ],
  "detail": {
    "state": [
      "running",
      "terminated"
    ]
  }
}
EOF
}

resource "aws_lambda_permission" "allow_cloudwatch_to_call_dns_lambda" {
    statement_id = "AllowExecutionFromCloudWatch"
    action = "lambda:InvokeFunction"
    function_name = aws_lambda_function.dynamic_dns.function_name
    principal = "events.amazonaws.com"
    source_arn = aws_cloudwatch_event_rule.ec2_running_terminated.arn
}

resource "aws_cloudwatch_event_target" "ddns-rule" {
  rule      = aws_cloudwatch_event_rule.ec2_running_terminated.name
  arn       = aws_lambda_function.dynamic_dns.arn
  depends_on = [aws_lambda_permission.allow_cloudwatch_to_call_dns_lambda]
}