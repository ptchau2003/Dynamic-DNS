#Environment
region = "us-east-1"
environment = "dev"

#Route 53
private_hosted_zone_name = "dev.vubiquity.cloud"
vpc_id = "vpc-0f6f613884bc62824"
record_type = "A"

#Lambda variables
lambda_name = "Dynamic_DNS_update"
python_filename = "DNS_update.zip"
handler_name = "DNS_update.lambda_handler"
lambda_timeout = 60
lambda_memory_size = 512
