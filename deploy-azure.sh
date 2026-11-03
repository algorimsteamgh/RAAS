#!/usr/bin/env bash

# ==============================================================================
# One-Click Production Deployment Script for Azure Infrastructure
# Targets: Azure Container Apps, Azure Container Registry, Azure Storage, Azure OpenAI
# ==============================================================================

set -euo pipefail

BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

echo -e "${BOLD}${CYAN}==================================================================${RESET}"
echo -e "${BOLD}${CYAN}   🚀 CV Screening & FDE Intelligence - Azure Production Deploy   ${RESET}"
echo -e "${BOLD}${CYAN}==================================================================${RESET}"

# 1. Configuration Defaults
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-rg-cvscreening-prod}"
LOCATION="${AZURE_LOCATION:-eastus}"
ENVIRONMENT="${AZURE_ENVIRONMENT:-prod}"
APP_NAME="${AZURE_APP_NAME:-cvscreen}"
DEPLOY_OPENAI="${DEPLOY_AZURE_OPENAI:-false}"
DEPLOY_VLLM_GPU="${DEPLOY_VLLM_GPU:-false}"

# 2. Check Prerequisites
echo -e "\n${BOLD}${CYAN}🔍 Step 1: Checking Azure CLI prerequisites...${RESET}"
if ! command -v az &> /dev/null; then
  echo -e "${RED}❌ Azure CLI (az) is not installed. Please install it: https://aka.ms/azure-cli${RESET}"
  exit 1
fi

if ! az account show > /dev/null 2>&1; then
  echo -e "${YELLOW}⚠️ You are not logged into Azure. Initiating login...${RESET}"
  az login
fi

CURRENT_SUB=$(az account show --query name -o tsv)
CURRENT_SUB_ID=$(az account show --query id -o tsv)
echo -e "${GREEN}✅ Authenticated to Azure Subscription:${RESET} ${BOLD}${CURRENT_SUB}${RESET} (${CURRENT_SUB_ID})"
echo -e "   Target Resource Group: ${BOLD}${RESOURCE_GROUP}${RESET}"
echo -e "   Target Location:       ${BOLD}${LOCATION}${RESET}"
echo -e "   Environment:           ${BOLD}${ENVIRONMENT}${RESET}"

# 3. Create Resource Group if not exists
echo -e "\n${BOLD}${CYAN}📦 Step 2: Ensuring Resource Group exists...${RESET}"
if az group exists --name "${RESOURCE_GROUP}" | grep -q "true"; then
  echo -e "${GREEN}✅ Resource Group '${RESOURCE_GROUP}' already exists.${RESET}"
else
  echo -e "${YELLOW}Creating Resource Group '${RESOURCE_GROUP}' in '${LOCATION}'...${RESET}"
  az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}" --tags Project="CVScreening-FDE" Environment="${ENVIRONMENT}" > /dev/null
  echo -e "${GREEN}✅ Resource Group created.${RESET}"
fi

# 3. Ensure ACR exists
echo -e "\n${BOLD}${CYAN}📦 Step 2b: Ensuring ACR exists...${RESET}"
ACR_NAME=$(az acr list --resource-group "${RESOURCE_GROUP}" --query "[0].name" -o tsv 2>/dev/null || true)
if [ -z "${ACR_NAME}" ]; then
  echo -e "${YELLOW}Provisioning Azure Container Registry...${RESET}"
  ACR_NAME=$(az deployment group create \
    --resource-group "${RESOURCE_GROUP}" \
    --template-file "infra/bicep/modules/acr.bicep" \
    --parameters location="${LOCATION}" environment="${ENVIRONMENT}" appName="${APP_NAME}" \
    --query properties.outputs.acrName.value -o tsv)
fi
ACR_LOGIN_SERVER=$(az acr show --name "${ACR_NAME}" --query loginServer -o tsv)
echo -e "${GREEN}✅ ACR Ready:${RESET} ${ACR_LOGIN_SERVER}"

# 4. Build & Push Docker Images
echo -e "\n${BOLD}${CYAN}🐳 Step 3: Building and pushing container images to ACR...${RESET}"

if command -v docker &> /dev/null && docker info &> /dev/null; then
  echo -e "   🔑 Authenticating local Docker to ${ACR_NAME}..."
  az acr login --name "${ACR_NAME}" > /dev/null

  echo -e "   🔨 Building Backend Container: ${ACR_LOGIN_SERVER}/cvscreening-backend:latest..."
  docker build --platform linux/amd64 -t "${ACR_LOGIN_SERVER}/cvscreening-backend:latest" -f Dockerfile.backend .
  echo -e "   📤 Pushing Backend Container to ACR..."
  docker push "${ACR_LOGIN_SERVER}/cvscreening-backend:latest"

  echo -e "   🔨 Building Frontend Container: ${ACR_LOGIN_SERVER}/cvscreening-frontend:latest..."
  docker build --platform linux/amd64 -t "${ACR_LOGIN_SERVER}/cvscreening-frontend:latest" -f Dockerfile.frontend .
  echo -e "   📤 Pushing Frontend Container to ACR..."
  docker push "${ACR_LOGIN_SERVER}/cvscreening-frontend:latest"
else
  echo -e "   🔨 Building Backend Container via ACR Cloud Tasks: ${ACR_LOGIN_SERVER}/cvscreening-backend:latest..."
  az acr build \
    --registry "${ACR_NAME}" \
    --image "cvscreening-backend:latest" \
    --file "Dockerfile.backend" \
    .

  echo -e "   🔨 Building Frontend Container via ACR Cloud Tasks: ${ACR_LOGIN_SERVER}/cvscreening-frontend:latest..."
  az acr build \
    --registry "${ACR_NAME}" \
    --image "cvscreening-frontend:latest" \
    --file "Dockerfile.frontend" \
    .
fi

# 5. Provision Core Azure Infrastructure via Bicep
echo -e "\n${BOLD}${CYAN}🏗️  Step 4: Provisioning Azure Infrastructure via Bicep...${RESET}"
echo -e "   (ACR, Storage Account, Log Analytics, Azure OpenAI, Container Apps Environment)"

DEPLOYMENT_NAME="cvscreening-infra-$(date +%s)"
ARM_OUTPUTS=$(az deployment group create \
  --resource-group "${RESOURCE_GROUP}" \
  --template-file "infra/bicep/main.bicep" \
  --name "${DEPLOYMENT_NAME}" \
  --parameters \
    location="${LOCATION}" \
    environment="${ENVIRONMENT}" \
    appName="${APP_NAME}" \
    deployAzureOpenAi="${DEPLOY_OPENAI}" \
    deployVllmGpu="${DEPLOY_VLLM_GPU}" \
  --query properties.outputs \
  -o json)

ACR_LOGIN_SERVER=$(echo "${ARM_OUTPUTS}" | jq -r '.acrLoginServer.value')
ACR_NAME=$(echo "${ACR_LOGIN_SERVER}" | cut -d'.' -f1)
BACKEND_URL=$(echo "${ARM_OUTPUTS}" | jq -r '.backendApiUrl.value')
FRONTEND_URL=$(echo "${ARM_OUTPUTS}" | jq -r '.applicationUrl.value')
STORAGE_ACCOUNT=$(echo "${ARM_OUTPUTS}" | jq -r '.storageAccountName.value // empty')
QWEN_ENGINE=$(echo "${ARM_OUTPUTS}" | jq -r '.qwenEngine.value // "vLLM-Qwen-GPU"')

echo -e "${GREEN}✅ Infrastructure Provisioned Successfully!${RESET}"
echo -e "   ACR Login Server: ${BOLD}${ACR_LOGIN_SERVER}${RESET}"
echo -e "   Storage Account:  ${BOLD}${STORAGE_ACCOUNT}${RESET}"
echo -e "   LLM Engine:       ${BOLD}${QWEN_ENGINE} (Open-Source Qwen, No API Keys Required)${RESET}"

# 6. Restart/Update Container Apps with fresh images
echo -e "\n${BOLD}${CYAN}🔄 Step 5: Updating Container Apps revisions...${RESET}"
BACKEND_APP_NAME="app-${APP_NAME}-backend-${ENVIRONMENT}"
FRONTEND_APP_NAME="app-${APP_NAME}-frontend-${ENVIRONMENT}"
VLLM_APP_NAME="app-${APP_NAME}-vllm-${ENVIRONMENT}"

if [ "${DEPLOY_VLLM_GPU:-false}" = "true" ]; then
  echo -e "   Updating vLLM GPU container app..."
  az containerapp update \
    --name "${VLLM_APP_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --image "${ACR_LOGIN_SERVER}/cvscreening-vllm-qwen:latest" > /dev/null || true
fi

az containerapp update \
  --name "${BACKEND_APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --image "${ACR_LOGIN_SERVER}/cvscreening-backend:latest" > /dev/null

az containerapp update \
  --name "${FRONTEND_APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --image "${ACR_LOGIN_SERVER}/cvscreening-frontend:latest" > /dev/null

# 7. Verification & Health Probes
echo -e "\n${BOLD}${CYAN}🩺 Step 6: Verifying Production Health Probes...${RESET}"
sleep 10

if curl -s -f "${BACKEND_URL}/healthz" > /dev/null 2>&1; then
  echo -e "${GREEN}✅ Backend Liveness Probe (${BACKEND_URL}/healthz): HEALTHY${RESET}"
else
  echo -e "${YELLOW}ℹ️  Backend is warming up... Check logs at: az containerapp logs show --name ${BACKEND_APP_NAME} -g ${RESOURCE_GROUP}${RESET}"
fi

if curl -s -f "${FRONTEND_URL}/healthz" > /dev/null 2>&1; then
  echo -e "${GREEN}✅ Frontend Liveness Probe (${FRONTEND_URL}/healthz): HEALTHY${RESET}"
else
  echo -e "${YELLOW}ℹ️  Frontend is warming up...${RESET}"
fi

echo -e "\n${BOLD}${GREEN}==================================================================${RESET}"
echo -e "${BOLD}${GREEN}   🎉 Production Deployment to Azure Completed Successfully!      ${RESET}"
echo -e "${BOLD}${GREEN}==================================================================${RESET}"
echo -e "${BOLD}Frontend Web Application:${RESET} ${CYAN}${FRONTEND_URL}${RESET}"
echo -e "${BOLD}Backend API Docs (Swagger):${RESET} ${CYAN}${BACKEND_URL}/docs${RESET}"
echo -e "${BOLD}Backend Health Probe:${RESET}      ${CYAN}${BACKEND_URL}/healthz${RESET}"
echo -e "${BOLD}Backend Readiness Check:${RESET}   ${CYAN}${BACKEND_URL}/readyz${RESET}"
