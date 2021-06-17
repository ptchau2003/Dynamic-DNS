#Global Variables
variable region {
    type = string
    description = "AWS region"
    default     = "us-east-1"
}
variable environment {
    type = string
    description = "Enviroments of SQS"
    default     = "dev"
}

#Route 53
variable vpc_id {
    type = string
    description = "Private hosted zone VPC"
    default     = "vpc-085d966300b165572"
}

variable private_hosted_zone_name {
    type = string
    description = "Private hosted zone"
    default     = "dev.vubiquity.cloud"
}

variable record_type {
    type = string
    description = "Record Type"
    default     = "A"
}
#Lambda variables
variable lambda_name {
    type = string
    description = "Function name of Lambda"
    default     = "DDNS"
}
variable python_filename {
    type = string
    description = "Python file of the code"
    default     = "DNS_update.zip"
}
variable handler_name {
    type = string
    description = "Handler function name"
    default     = "DDNS_update.lambda_handler"
}
variable lambda_memory_size {
    type = number
    description = "Lambda memory size"
    default     = 512
}
variable lambda_timeout {
    type = number
    description = "Lambda function timeout"
    default     = 60
}
