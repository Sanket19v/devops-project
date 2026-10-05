terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

variable "region" { default = "us-east-1" }

# The optimizer rewrites this map (right-size / remove idle) into optimized.tfvars.json
variable "instances" {
  type = map(object({ type = string }))
  default = {
    "web-1"   = { type = "t3.small" }
    "batch-1" = { type = "t3.micro" }
  }
}

provider "aws" { region = var.region }

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-2023*-x86_64"]
  }
}

resource "aws_instance" "this" {
  for_each      = var.instances
  ami           = data.aws_ami.al2023.id
  instance_type = each.value.type
  tags          = { Name = each.key }
}

# Deliberately wasteful: an unattached volume for the optimizer to find
resource "aws_ebs_volume" "orphan" {
  availability_zone = "${var.region}a"
  size              = 10
  type              = "gp3"
  tags              = { Name = "orphan-demo" }
}
