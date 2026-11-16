data "aws_partition" "current" {}

locals {
  has_image   = var.api_image_tag != ""
  api_image   = "${aws_ecr_repository.api.repository_url}:${local.has_image ? var.api_image_tag : "none"}"
  api_port    = 8000
  zone_id     = var.hosted_zone_id != "" ? var.hosted_zone_id : aws_route53_zone.main[0].zone_id
  origin_fqdn = "${var.origin_subdomain}.${var.domain_name}"
}
