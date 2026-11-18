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
   to 2 tasks. After that, the GitHub deploy workflow registers new
   task-definition revisions and Terraform ignores `task_definition` on the
   services, so a later apply does not roll a deploy back. Set
   `worker_desired_count` to 1 or more once the image is in ECR. Run
   migrations / the data load (it reads the SQLite file from
   `s3://<cv bucket>/migration/`) with the `migrate` task:
   ```
   aws ecs run-task --cluster raas-prod --task-definition raas-prod-migrate --launch-type FARGATE \
     --network-configuration "awsvpcConfiguration={subnets=[APP-SUBNET-ID],securityGroups=[APP-SG-ID]}"
   ```
4. **Custom domain** (on by default since go-live on 17 Nov 2026).
   `enable_custom_domain` creates the ACM certificates, switches the ALB to
   HTTPS on `origin.raashiring.com` and gives CloudFront raashiring.com and
   www. The certificates validate through DNS records that must resolve
   publicly, and CloudFront reaches the ALB through `origin.raashiring.com`,
   which must resolve too (or the API returns 502). At go-live the zone was
   still on Azure DNS, so the three validation CNAMEs and an `origin` CNAME to
   the ALB were copied there before GoDaddy's name servers moved to Route 53.
5. **Cut-over** (done 17 Nov 2026). `point_dns_to_aws` creates the apex and
   www alias records to CloudFront in Route 53. Test on
   `cloudfront_domain_name` first. Rollback while Azure is kept: point the
   apex and www records in Route 53 back to Azure (or GoDaddy's name servers
   back to Azure DNS), then start the Azure backend.
6. **Liftproof.** `terraform output liftproof_create_stack_parameters` gives
   the Part C2 parameters. After the stack exists, set
   `liftproof_security_group_id` and `liftproof_instance_role_name` (Part D3)
   and apply, instead of running the D3 commands by hand.

## Application

The app changes for AWS (Bedrock, PostgreSQL, S3, SQS, worker, data load) are
in PR #6; see `docs/aws/APP_ON_AWS.md` there. The containers get
`DATABASE_HOST/PORT/NAME/USER/PASSWORD`, `DATABASE_SECRET_ARN`,
`DATABASE_SSLMODE=require`, `CV_BUCKET`, `BATCH_QUEUE_URL`,
`MODEL_BACKEND=bedrock`, `BEDROCK_MODEL_ID`, `BEDROCK_GUARDRAIL_ID`,
`BEDROCK_GUARDRAIL_VERSION` and `SEED_DEMO_DATA=false`. The worker runs
`python -m backend.app.worker`, the migrate task
`python -m backend.app.db.migrate`.

## Interim site password (until Cognito)

The API has no sign-in of its own. Until Cognito arrives, set
`site_password_enabled = true` (and optionally `allowed_countries`) and apply:
CloudFront then asks for one shared HTTP Basic username and password before
any page, asset or `/api` call (only `/api/system/health` stays open for the
deploy smoke test). Read it with `terraform output site_username` and
`terraform output -raw site_password`, share it only through a password
manager, and rotate it with `terraform apply -replace=random_password.site`.
Turning it off is `site_password_enabled = false` and apply. Scripts and
Playwright (Liftproof journeys) pass it with `curl -u` / `httpCredentials`.

## Bedrock

Task roles may call the models in `bedrock_foundation_model_ids` (Claude
Sonnet 5 by default, the only text model on demand in ap-southeast-1 as of
17 Nov 2026; the first entry is the app's `BEDROCK_MODEL_ID`). Cross-region inference
profiles are denied unless listed in `bedrock_inference_profile_ids`
(decision D2). Call the model once with an admin profile (`aws bedrock-runtime
converse --model-id anthropic.claude-sonnet-5 ...`) so that any one-time use-case
form or Marketplace subscription is done before the app calls it.

Fallback if Sonnet 5 is not enabled for the account (needs Quess Global's OK on
D2, because a global profile may process data outside APAC): add to
`terraform.tfvars`

```
bedrock_inference_profile_ids = ["global.anthropic.claude-haiku-4-5-20251001-v1:0"]
```

and apply. The first listed profile becomes the app's `BEDROCK_MODEL_ID`, and
the task roles may call it. Then re-run the deploy workflow, so the services
pick up the new task-definition revision. Remove the line to go back.

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
