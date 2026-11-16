# RAASHiring on AWS (Terraform)

First slice of the AWS production setup in ap-southeast-1: the network, the
PostgreSQL database and the CV bucket. ECS, the load balancer, CloudFront,
SQS and the deploy pipeline are added in later changes.

| File | Creates |
|---|---|
| `network.tf` | VPC, 2 public / 2 app / 2 data subnets, NAT gateway, S3 gateway endpoint, app security group |
| `data.tf` | KMS key, RDS for PostgreSQL 16 (Multi-AZ, encrypted, TLS enforced, 35-day backups), CV bucket |
| `outputs.tf` | Values the application, the data load and Liftproof need |

Running cost once applied: about USD 160 a month for the database, about
USD 45 for the NAT gateway, about USD 1 for the key.

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
