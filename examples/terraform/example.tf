terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"  # This is UNBOUND - dangerous!
    }
    kubernetes = {
      source  = "hashicorp/kubernetes" 
      version = "~> 2.0"    # This is BOUND - safe
    }
    random = {
      source  = "hashicorp/random"
      version = "*"         # This is UNBOUND - very dangerous!
    }
  }
}

provider "aws" {
  region = "us-west-2"
}

resource "aws_instance" "example" {
  ami           = "ami-12345678"
  instance_type = "t2.micro"
}