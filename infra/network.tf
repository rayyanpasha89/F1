resource "aws_vpc" "project" {

  cidr_block           = "10.84.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = {
    Name = local.name
  }


}

resource "aws_internet_gateway" "project" {
  vpc_id = aws_vpc.project.id
}

resource "aws_subnet" "public" {

  count             = 2
  vpc_id            = aws_vpc.project.id
  cidr_block        = "10.84.${count.index}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

}

resource "aws_subnet" "private" {

  count             = 2
  vpc_id            = aws_vpc.project.id
  cidr_block        = "10.84.${count.index + 10}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

}

resource "aws_route_table" "public" {

  vpc_id = aws_vpc.project.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.project.id

  }


}

resource "aws_route_table_association" "public" {

  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id

}

resource "aws_security_group" "alb" {

  name   = "${local.name}-alb"
  vpc_id = aws_vpc.project.id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["10.84.0.0/16"]

  }


}

data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_vpc_security_group_ingress_rule" "cloudfront" {

  security_group_id = aws_security_group.alb.id
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80

}

resource "aws_security_group" "task" {

  name   = "${local.name}-task"
  vpc_id = aws_vpc.project.id
  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]

  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]

  }


}

resource "aws_security_group" "db" {

  name   = "${local.name}-database"
  vpc_id = aws_vpc.project.id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.task.id]

  }


}

resource "aws_db_subnet_group" "project" {

  name       = local.name
  subnet_ids = aws_subnet.private[*].id

}

resource "aws_db_instance" "project" {

  identifier                      = local.name
  engine                          = "postgres"
  engine_version                  = "16.15"
  instance_class                  = "db.t4g.micro"
  allocated_storage               = 20
  max_allocated_storage           = 30
  storage_type                    = "gp3"
  storage_encrypted               = true
  db_name                         = "f1"
  username                        = "f1admin"
  manage_master_user_password     = true
  db_subnet_group_name            = aws_db_subnet_group.project.name
  vpc_security_group_ids          = [aws_security_group.db.id]
  publicly_accessible             = false
  backup_retention_period         = 7
  deletion_protection             = true
  skip_final_snapshot             = false
  final_snapshot_identifier       = "${local.name}-final"
  auto_minor_version_upgrade      = true
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  lifecycle {
    prevent_destroy = true
  }


}

