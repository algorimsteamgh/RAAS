# Deploying CVScreen to a new Azure subscription

CVScreen deploys with `deploy-azure.sh` and the Bicep templates in `infra/bicep`. Nothing in them is tied to a particular subscription: resource names are derived from the resource group, so the same code works in any account. Region defaults to Singapore (`southeastasia`).

## What gets created

In resource group `rg-cvscreening-prod`:

- Log Analytics workspace and Application Insights
- Storage account with Azure Files shares `cv-data` (SQLite snapshots) and `cv-models`, and blob containers `cv-resumes`, `cv-extracted`
- Azure Container Registry (Standard)
- Container Apps environment with:
  - `app-cvscreen-backend-prod`: FastAPI + Ollama with Qwen 2.5 1.5B baked into the image, internal ingress only, 2 vCPU / 4 GiB, scales 0-1 (single SQLite writer)
  - `app-cvscreen-frontend-prod`: React + nginx, public HTTPS, proxies `/api` to the backend

## One-time setup

1. Sign in as an Owner of the new subscription and run:

   ```bash
   az login --tenant <tenant-id>
   ./scripts/bootstrap-azure-subscription.sh <subscription-id>
   ```

   This registers the resource providers, creates an Entra ID app that GitHub Actions signs in as through OIDC (no client secret to store or rotate), and gives it Contributor on the subscription.

2. In GitHub, go to Settings > Environments, create `production`, and add the three secrets the script prints: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`. Optionally add variables `AZURE_LOCATION` or `AZURE_RESOURCE_GROUP` to override the defaults.

## Deploy

Actions > **Deploy to Azure** > Run workflow. It builds both images, tags them with the commit SHA, provisions or updates the infrastructure, rolls the Container Apps to the new images, and prints the public URL in the run summary.

You can also run it from a laptop after `az login`:

```bash
AZURE_LOCATION=southeastasia ./deploy-azure.sh
```

## Check it

```bash
curl https://<frontend-fqdn>/healthz             # nginx
curl https://<frontend-fqdn>/api/system/health   # backend, Ollama and SQLite
```

The backend scales to zero, so the first request after idle can take a minute while Ollama loads the model.

## Notes

- On the earlier Free Trial subscription the Container Apps environment quota was 1. If a failed deployment leaves an environment behind, delete it before retrying (see `DEPLOYMENT_PHASE_D_QUOTA_BLOCKER.md`).
- ACR Standard costs about $20/month after trial credits. Change `acrSku` in `infra/bicep/main.bicep` to `Basic` (about $5/month) if you don't need Standard's storage or throughput.
- Data does not move with the code. To bring candidates from the old subscription, copy `cv_screening.db` from its `cv-data` file share into the new one before the backend first starts.
