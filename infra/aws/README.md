# RAASHiring on AWS (Terraform)

The AWS production setup for RAASHiring in Quess Global's account
007477962703, ap-southeast-1. One root module; Terraform refuses to run
against any other account (`allowed_account_ids`).

| File | Creates |
|---|---|
| `network.tf` | VPC, 2 public / 2 app / 2 data subnets, NAT gateway, S3 gateway endpoint, app security group |
| `data.tf` | KMS key, RDS for PostgreSQL 16 (Multi-AZ, encrypted, TLS enforced, 35-day backups), CV bucket |
| `security_groups.tf` | ALB group (CloudFront origin-facing prefix list only), ALB to tasks on 8000, optional Liftproof to RDS on 5432 |
| `sqs_ecr.tf` | Batch SQS queue + dead-letter queue (3 attempts), ECR repository (immutable tags, scan on push) |
| `iam_app.tf` | ECS execution role, API and worker task roles (CV bucket, SQS, DB secret, Bedrock Converse), optional Liftproof read on the CV bucket |
| `ecs.tf` | Fargate cluster, API service (2–6 tasks, CPU and request autoscaling), worker service, one-off `migrate` task |
| `alb.tf` | Internet-facing ALB that forwards only requests carrying CloudFront's secret `X-Origin-Verify` header; access logs |
| `frontend.tf` | Private S3 bucket for the React build (read by CloudFront through OAC) |
| `edge.tf` | CloudFront (SPA from S3, `/api/*` to the ALB uncached), SPA rewrite function, WAF web ACL in us-east-1 |
| `dns.tf` | Route 53 zone for raashiring.com, ACM certificates, origin record, cut-over alias records |
| `github_oidc.tf` | GitHub Actions OIDC provider and deploy role (main branch / production environment only) |
| `logging.tf` | KMS key for CloudWatch Logs, VPC flow logs |
| `operations.tf` | SNS alarm topic and alarms, AWS Backup (daily, 90 days), CloudTrail, GuardDuty, Security Hub |
| `outputs.tf` | Values the application, the data load, CI and Liftproof need |
| `tests/` | `terraform test` with mocked providers (no AWS access needed) |

Running cost: about USD 160 a month for the database and USD 45 for the NAT
gateway (the first slice), plus roughly USD 70 for two API tasks, USD 20 for
the ALB, and small amounts for logs, KMS, WAF, Backup and GuardDuty. The
CloudFront flat-rate Pro plan (USD 15, includes WAF) is chosen in the
CloudFront console; it is not a Terraform resource.

## Deploy

Run from this folder, signed in to the target AWS account.

```
export AWS_PROFILE=quess AWS_REGION=ap-southeast-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
```

Create the state bucket once:

```
aws s3api create-bucket --bucket raas-tfstate-$ACCOUNT-ap-southeast-1 --create-bucket-configuration LocationConstraint=ap-southeast-1
aws s3api put-bucket-versioning --bucket raas-tfstate-$ACCOUNT-ap-southeast-1 --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket raas-tfstate-$ACCOUNT-ap-southeast-1 --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

Then:

```
terraform init -backend-config="bucket=raas-tfstate-$ACCOUNT-ap-southeast-1"
terraform plan -out raas.tfplan
terraform apply raas.tfplan
terraform output
```

The database takes about 15 minutes to create. Its master password is
created by RDS in Secrets Manager (`db_master_secret_arn`) and is never in
Terraform state.

Needs Terraform 1.10 or newer.

## Applying in stages (go-live week)

Everything has a safe default, so a plain `terraform apply` works at every
stage. Copy `terraform.tfvars.example` to `terraform.tfvars` and turn things on
as the week goes:

1. **First apply.** Network, database, CV bucket, ECR, SQS, ECS (0 tasks:
   there is no image yet), ALB, CloudFront on its default `*.cloudfront.net`
   name, WAF, and the Route 53 zone. If only the network and database are
   wanted first:
   `terraform apply -target=aws_db_instance.main -target=aws_s3_bucket_policy.cvs -target=aws_vpc_endpoint.s3 -target=aws_route_table_association.app`
2. **DNS delegation.** Copy today's GoDaddy records into the new zone (they
   still point at Azure), then set GoDaddy's name servers to
   `terraform output route53_name_servers`. If a zone already exists, set
   `hosted_zone_id` instead and Terraform will not create one.
3. **First image.** Push the API image to `ecr_repository_url` tagged with
   the commit SHA, set `api_image_tag`, apply. Autoscaling raises the API
   to 2 tasks. Run migrations / the data load with the `migrate` task:
   ```
   aws ecs run-task --cluster raas-prod --task-definition raas-prod-migrate --launch-type FARGATE \
     --network-configuration "awsvpcConfiguration={subnets=[APP-SUBNET-ID],securityGroups=[APP-SG-ID]}"
   ```
4. **Custom domain.** Once the name servers have moved, set
   `enable_custom_domain = true`: ACM certificates validate through Route 53,
   the ALB switches to HTTPS on `origin.raashiring.com`, CloudFront gets
   raashiring.com and www.
5. **Cut-over (Thu 19 Nov).** Test on `cloudfront_domain_name` first. Delete
   the Azure `www` CNAME if there is one (an alias A record cannot sit next
   to a CNAME), then set `point_dns_to_aws = true`. Rollback: set it back to
   false and re-create the Azure records.
6. **Liftproof.** `terraform output liftproof_create_stack_parameters` gives
   the Part C2 parameters. After the stack exists, set
   `liftproof_security_group_id` and `liftproof_instance_role_name` (Part D3)
   and apply, instead of running the D3 commands by hand.

## What the application needs to change

The container gets `DATABASE_HOST/PORT/NAME/USER/PASSWORD`,
`DATABASE_SSLMODE=require`, `CV_BUCKET`, `BATCH_QUEUE_URL`,
`MODEL_BACKEND=bedrock`, `BEDROCK_MODEL_ID` and `SEED_DEMO_DATA=false`. The
code still uses SQLite and Ollama; the Bedrock, PostgreSQL, S3 and SQS
changes are separate work. The worker service stays at 0 tasks
(`worker_desired_count`) until the image has a worker entry point
(`worker_command`, default `python -m app.worker`).

## Bedrock

Task roles may call the models in `bedrock_foundation_model_ids` (Nova Lite
and Claude 3 Haiku by default, in-region on-demand). Cross-region inference
profiles are denied unless listed in `bedrock_inference_profile_ids`
(decision D2). Model access must also be enabled once in the Bedrock console.

## Account services

`enable_account_security_services` (CloudTrail, GuardDuty, Security Hub)
and `create_github_oidc_provider` default to true for a fresh account. Set
them to false if Quess Global's AWS Organization already provides them,
otherwise the apply fails with "already exists".

## Tests

```
terraform init -backend=false
terraform test
```
