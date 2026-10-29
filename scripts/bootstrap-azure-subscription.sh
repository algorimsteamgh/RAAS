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

add_federated_credential() {
  local name="$1" subject="$2"
  if ! az ad app federated-credential list --id "$CLIENT_ID" --query "[?name=='${name}'].name" -o tsv | grep -q .; then
    az ad app federated-credential create --id "$CLIENT_ID" --parameters "{
      \"name\": \"${name}\",
      \"issuer\": \"https://token.actions.githubusercontent.com\",
      \"subject\": \"${subject}\",
      \"audiences\": [\"api://AzureADTokenExchange\"]
    }" -o none
  fi
}

add_federated_credential "github-${GITHUB_ENVIRONMENT}" "repo:${GITHUB_REPO}:environment:${GITHUB_ENVIRONMENT}"

# Newer GitHub orgs and repos send a subject that includes the owner and repo IDs,
# e.g. repo:owner@123/name@456:environment:production, so register that form too.
REPO_JSON="$(curl -fsSL "https://api.github.com/repos/${GITHUB_REPO}" || true)"
OWNER_ID="$(echo "$REPO_JSON" | jq -r '.owner.id // empty' 2>/dev/null || true)"
REPO_ID="$(echo "$REPO_JSON" | jq -r '.id // empty' 2>/dev/null || true)"
if [ -n "$OWNER_ID" ] && [ -n "$REPO_ID" ]; then
  add_federated_credential "github-${GITHUB_ENVIRONMENT}-ids" \
    "repo:${GITHUB_REPO%%/*}@${OWNER_ID}/${GITHUB_REPO#*/}@${REPO_ID}:environment:${GITHUB_ENVIRONMENT}"
else
  echo "Could not look up ${GITHUB_REPO} on GitHub; if sign-in fails with AADSTS700213,"
  echo "add a federated credential with the subject shown in that error."
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
