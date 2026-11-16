# Route 53 zone for raashiring.com, ACM certificates, and the records.
#
# Order:
#  1. First apply: zone created (unless hosted_zone_id is given). Copy today's
#     GoDaddy records into it (they keep pointing at Azure), then set GoDaddy's
#     name servers to the route53_name_servers output.
#  2. enable_custom_domain = true: certificates validate through the zone, the
#     ALB gets HTTPS on origin.<domain>, CloudFront gets the site aliases.
#  3. Cut-over: point_dns_to_aws = true switches apex and www to CloudFront.
#     Rollback: set it back to false and re-create the Azure records.

resource "aws_route53_zone" "main" {
  count   = var.hosted_zone_id == "" ? 1 : 0
  name    = var.domain_name
  comment = "RAASHiring public zone (managed by Terraform)"
}

# Viewer certificate for CloudFront (must be us-east-1).
resource "aws_acm_certificate" "site" {
  count                     = var.enable_custom_domain ? 1 : 0
  provider                  = aws.us_east_1
  domain_name               = var.domain_name
  subject_alternative_names = ["www.${var.domain_name}"]
  validation_method         = "DNS"
  lifecycle {
    create_before_destroy = true
  }
}

# Regional certificate for the ALB origin hostname.
resource "aws_acm_certificate" "origin" {
  count             = var.enable_custom_domain ? 1 : 0
  domain_name       = local.origin_fqdn
  validation_method = "DNS"
  lifecycle {
    create_before_destroy = true
  }
}

locals {
  acm_validation_records = var.enable_custom_domain ? merge(
    { for o in aws_acm_certificate.site[0].domain_validation_options : o.domain_name => o },
    { for o in aws_acm_certificate.origin[0].domain_validation_options : o.domain_name => o },
  ) : {}
}

resource "aws_route53_record" "acm_validation" {
  for_each        = local.acm_validation_records
  zone_id         = local.zone_id
  name            = each.value.resource_record_name
  type            = each.value.resource_record_type
  records         = [each.value.resource_record_value]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "site" {
  count                   = var.enable_custom_domain ? 1 : 0
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.site[0].arn
  validation_record_fqdns = [for d in [var.domain_name, "www.${var.domain_name}"] : aws_route53_record.acm_validation[d].fqdn]
}

resource "aws_acm_certificate_validation" "origin" {
  count                   = var.enable_custom_domain ? 1 : 0
  certificate_arn         = aws_acm_certificate.origin[0].arn
  validation_record_fqdns = [aws_route53_record.acm_validation[local.origin_fqdn].fqdn]
}

# origin.<domain> -> ALB (not user-facing; the ALB rejects direct requests).
resource "aws_route53_record" "origin" {
  count   = var.enable_custom_domain ? 1 : 0
  zone_id = local.zone_id
  name    = local.origin_fqdn
  type    = "A"
  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = false
  }
}

# Cut-over records. allow_overwrite replaces the Azure A/AAAA/CNAME copies.
resource "aws_route53_record" "site" {
  for_each = var.enable_custom_domain && var.point_dns_to_aws ? {
    apex_a    = { name = var.domain_name, type = "A" }
    apex_aaaa = { name = var.domain_name, type = "AAAA" }
    www_a     = { name = "www.${var.domain_name}", type = "A" }
    www_aaaa  = { name = "www.${var.domain_name}", type = "AAAA" }
  } : {}
  zone_id         = local.zone_id
  name            = each.value.name
  type            = each.value.type
  allow_overwrite = true
  alias {
    name                   = aws_cloudfront_distribution.main.domain_name
    zone_id                = aws_cloudfront_distribution.main.hosted_zone_id
    evaluate_target_health = false
  }
}
