targetScope = 'resourceGroup'

@description('Azure Region for all resources')
param location string = resourceGroup().location

@description('Azure Region for Container Apps Managed Environment (decoupled to avoid eastus capacity limits)')
param containerAppsLocation string = 'eastus2'

@description('Deployment Environment')
@allowed([
  'dev'
  'staging'
  'prod'
])
param environment string = 'prod'

@description('Application Name prefix')
param appName string = 'cvscreen'

@description('Deploy dedicated Azure GPU Container running vLLM for Qwen')
param deployVllmGpu bool = false

@description('Qwen model identifier to serve in vLLM')
param qwenModelName string = 'Qwen/Qwen2.5-7B-Instruct'

@description('Deploy Azure OpenAI Service instance (set true if using Azure OpenAI instead of Qwen)')
param deployAzureOpenAi bool = false

@description('Existing Azure OpenAI Endpoint (if deployAzureOpenAi is false)')
param existingOpenAiEndpoint string = ''

@description('Existing Azure OpenAI API Key (if deployAzureOpenAi is false)')
@secure()
param existingOpenAiApiKey string = ''

@description('Tag metadata for Azure cost tracking')
param tags object = {
  Project: 'CVScreening-FDE'
  ManagedBy: 'Bicep'
  Environment: environment
  LLMEngine: deployVllmGpu ? 'vLLM-Qwen-GPU' : 'AzureOpenAI'
}

// 1. Log Analytics & Application Insights
module monitoring 'modules/log-analytics.bicep' = {
  name: 'monitoringDeployment'
  params: {
    location: location
    environment: environment
    appName: appName
  }
}

// 2. Storage Account (Blob Containers + Azure Files for SQLite & Models)
module storage 'modules/storage.bicep' = {
  name: 'storageDeployment'
  params: {
    location: location
    environment: environment
    appName: appName
  }
}

// 3. Azure Container Registry
module acr 'modules/acr.bicep' = {
  name: 'acrDeployment'
  params: {
    location: location
    environment: environment
    appName: appName
    acrSku: 'Standard'
  }
}

// 4. Optional Azure OpenAI Service
module openai 'modules/openai.bicep' = if (deployAzureOpenAi) {
  name: 'openaiDeployment'
  params: {
    location: location
    environment: environment
    appName: appName
    deployGpt4oMini: true
    deployEmbedding: true
  }
}

var openAiEndpoint = deployAzureOpenAi ? (openai.?outputs.endpoint ?? '') : existingOpenAiEndpoint
var openAiApiKey = deployAzureOpenAi ? (openai.?outputs.apiKey ?? '') : existingOpenAiApiKey
var openAiDeploymentName = deployAzureOpenAi ? (openai.?outputs.gptDeploymentName ?? '') : 'gpt-4o-mini'
var openAiApiVersion = deployAzureOpenAi ? (openai.?outputs.apiVersion ?? '') : '2024-08-01-preview'

// 5. Azure Container Apps (Managed Environment + Backend + Frontend)
module containerApps 'modules/container-apps.bicep' = {
  name: 'containerAppsDeployment'
  params: {
    location: containerAppsLocation
    environment: environment
    appName: appName
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsId
    logAnalyticsCustomerId: monitoring.outputs.logAnalyticsCustomerId
    logAnalyticsSharedKey: monitoring.outputs.logAnalyticsSharedKey
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    acrLoginServer: acr.outputs.loginServer
    acrUsername: acr.outputs.adminUsername
    acrPassword: acr.outputs.adminPassword
    backendImage: '${acr.outputs.loginServer}/cvscreening-backend:latest'
    frontendImage: '${acr.outputs.loginServer}/cvscreening-frontend:latest'
    storageAccountName: storage.outputs.storageAccountName
    storageAccountKey: storage.outputs.storageAccountKey
    fileShareName: storage.outputs.fileShareName
    storageConnectionString: storage.outputs.connectionString
    modelBackend: deployVllmGpu ? 'vllm' : (deployAzureOpenAi ? 'azure_openai' : 'ollama')
    vllmBaseUrl: deployVllmGpu ? 'http://app-${appName}-vllm-${environment}:8000/v1' : ''
    azureOpenAiEndpoint: openAiEndpoint
    azureOpenAiApiKey: openAiApiKey
    azureOpenAiDeploymentName: openAiDeploymentName
    azureOpenAiApiVersion: openAiApiVersion
  }
}

// 6. Dedicated GPU Container App running vLLM for Qwen (Internal Service)
module vllmGpu 'modules/vllm-gpu.bicep' = if (deployVllmGpu) {
  name: 'vllmGpuDeployment'
  params: {
    location: location
    environment: environment
    appName: appName
    managedEnvironmentId: containerApps.outputs.environmentId
    acrLoginServer: acr.outputs.loginServer
    acrUsername: acr.outputs.adminUsername
    acrPassword: acr.outputs.adminPassword
    vllmImage: '${acr.outputs.loginServer}/cvscreening-vllm-qwen:latest'
    modelStorageMountName: 'cvdatamount'
    modelName: qwenModelName
  }
}

output applicationUrl string = containerApps.outputs.frontendUrl
output backendApiUrl string = containerApps.outputs.backendUrl
output acrLoginServer string = acr.outputs.loginServer
output storageAccountName string = storage.outputs.storageAccountName
output qwenEngine string = deployVllmGpu ? 'vLLM Dedicated GPU (Internal)' : 'External / API'
output vllmInternalUrl string = deployVllmGpu ? 'http://app-${appName}-vllm-${environment}:8000/v1' : ''
output appInsightsConnectionString string = monitoring.outputs.appInsightsConnectionString
