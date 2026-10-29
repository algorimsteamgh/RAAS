#!/usr/bin/env bash
# One-time setup so GitHub Actions can deploy CVScreen into a new Azure subscription.
# Run it yourself after `az login`, as a user who is Owner of the subscription:
#
#   ./scripts/bootstrap-azure-subscription.sh <subscription-id> [github-repo]
#
# It registers the resource providers CVScreen needs, creates an Entra ID app that
# GitHub Actions signs in as through OIDC (no client secret), gives it Contributor
# on the subscription, and prints the GitHub secrets to add.
set -euo pipefail

SUBSCRIPTION_ID="${1:?usage: bootstrap-azure-subscription.sh <subscription-id> [github-repo]}"
GITHUB_REPO="${2:-algorimsteamgh/RAAS}"
GITHUB_ENVIRONMENT="production"
APP_NAME="cvscreen-github-actions"

az account set --subscription "$SUBSCRIPTION_ID"
TENANT_ID="$(az account show --query tenantId -o tsv)"

echo "Registering resource providers (can take a few minutes)..."
for ns in Microsoft.App Microsoft.ContainerRegistry Microsoft.Storage Microsoft.OperationalInsights Microsoft.Insights; do
  az provider register --namespace "$ns" --wait >/dev/null
done

echo "Creating Entra ID app for GitHub Actions..."
CLIENT_ID="$(az ad app list --display-name "$APP_NAME" --query '[0].appId' -o tsv)"
if [ -z "$CLIENT_ID" ]; then
  CLIENT_ID="$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)"
fi
az ad sp show --id "$CLIENT_ID" >/dev/null 2>&1 || az ad sp create --id "$CLIENT_ID" -o none
SP_OBJECT_ID="$(az ad sp show --id "$CLIENT_ID" --query id -o tsv)"

if ! az ad app federated-credential list --id "$CLIENT_ID" --query "[?name=='github-${GITHUB_ENVIRONMENT}'].name" -o tsv | grep -q .; then
  az ad app federated-credential create --id "$CLIENT_ID" --parameters "{
    \"name\": \"github-${GITHUB_ENVIRONMENT}\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"repo:${GITHUB_REPO}:environment:${GITHUB_ENVIRONMENT}\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }" -o none
fi

echo "Granting Contributor on the subscription..."
az role assignment create --assignee-object-id "$SP_OBJECT_ID" --assignee-principal-type ServicePrincipal \
  --role "Contributor" --scope "/subscriptions/${SUBSCRIPTION_ID}" -o none

cat <<OUT

Done. In ${GITHUB_REPO}, go to Settings > Environments, create "${GITHUB_ENVIRONMENT}",
and add these secrets:

  AZURE_CLIENT_ID          ${CLIENT_ID}
  AZURE_TENANT_ID          ${TENANT_ID}
  AZURE_SUBSCRIPTION_ID    ${SUBSCRIPTION_ID}

Optional environment variables (defaults shown):

  AZURE_LOCATION           southeastasia
  AZURE_RESOURCE_GROUP     rg-cvscreening-prod
OUT
