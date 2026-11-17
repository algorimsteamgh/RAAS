# Running RAASHiring on AWS

One image (`Dockerfile.backend`, ECR `raas/api`, tag = commit SHA) runs three
ways on ECS Fargate (task definitions in `infra/aws/ecs.tf`):

| task | command |
|---|---|
| API (service `api`) | default CMD: uvicorn on port 8000, health `/healthz`, readiness `/readyz` (checks the database) |
| worker (service `worker`) | `python -m backend.app.worker` |
| migrate (one-off) | `python -m backend.app.db.migrate` (Alembic upgrade); also runs the data load |

## Configuration (environment variables)

| variable | meaning |
|---|---|
| `APP_ENV` | `prod` in AWS; `local`/`test` turn on demo seed data and auto-migrate |
| `DATABASE_HOST/PORT/NAME/USER/PASSWORD`, `DATABASE_SSLMODE` | PostgreSQL. Or `DATABASE_URL`. |
| `DATABASE_SECRET_ARN` | optional: read user/password from the RDS secret and re-read after a rotation |
| `CV_BUCKET`, `CV_BUCKET_KMS_KEY_ID` | S3 CV storage (SSE-KMS). Without `CV_BUCKET`, files go to `data/cv_store/` |
| `BATCH_QUEUE_URL` | SQS batch queue. Without it, batches run inside the API process |
| `MODEL_BACKEND` | `bedrock` (AWS) or `ollama` (local / Qwen baseline) |
| `BEDROCK_MODEL_ID` | extraction and chat model; production uses `anthropic.claude-sonnet-5` (in-region in ap-southeast-1), set by Terraform |
| `BEDROCK_CHAT_MODEL_ID` | optional, HR chat model (default: `BEDROCK_MODEL_ID`) |
| `BEDROCK_GUARDRAIL_ID`, `BEDROCK_GUARDRAIL_VERSION` | optional guardrail on the HR chat |
| `SEED_DEMO_DATA` | `false` in production (also disables `POST /api/dataset/load-mock`) |
| `WORKER_CONCURRENCY` | files a worker task processes at once (default 4) |

## Data load (rehearsals Mon 16 and Tue 17 Nov, final load Thu 19 Nov)

1. Copy the SQLite freeze (`cv_screening.db` from the Azure `cv-data` share,
   after writes are stopped) to `s3://raas-cvs-007477962703-ap-southeast-1/migration/cv_screening.db`.
2. Run the migrate task with a command override:
   ```
   aws ecs run-task --cluster raas-prod --task-definition raas-prod-migrate --launch-type FARGATE \
     --network-configuration "awsvpcConfiguration={subnets=[APP-SUBNET-ID],securityGroups=[APP-SG-ID]}" \
     --overrides '{"containerOverrides":[{"name":"migrate","command":["python","-m","backend.app.dataload.sqlite_to_postgres",
       "--sqlite","s3://raas-cvs-007477962703-ap-southeast-1/migration/cv_screening.db",
       "--report","s3://raas-cvs-007477962703-ap-southeast-1/migration/reports/","--truncate"]}]}'
   ```
   Add `"--exclude-source","MOCK"` if Quess Global decides to drop the 500
   seed candidates (Q8). Use `--truncate` for rehearsals and the final load;
   without it the job refuses a non-empty database.
3. Read the summary in CloudWatch `/raas/prod/migrate` and the JSON report in
   `migration/reports/`. Exit code 0 = every check passed. `--verify-only`
   re-runs the checks without loading.
4. Delete `migration/` objects after sign-off.

## Model choice

Set `MODEL_BACKEND`/`BEDROCK_MODEL_ID` and call
`GET /api/evaluation/metrics`, or run the CV agent over `dataset/ground_truth`
with each model. Both candidate models are allowed by the task role.
