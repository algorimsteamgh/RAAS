@description('Azure Region for Azure OpenAI (e.g. eastus, swedencentral, westus3)')
param location string

@description('Environment prefix, e.g. dev, staging, prod')
param environment string

@description('Application name prefix')
param appName string

@description('Deploy GPT-4o-mini model')
param deployGpt4oMini bool = true

@description('Deploy text-embedding-3-small model')
param deployEmbedding bool = true

var openAiAccountName = 'oai-${appName}-${environment}-${uniqueString(resourceGroup().id)}'
var cleanOpenAiName = take(toLower(openAiAccountName), 64)

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: cleanOpenAiName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: cleanOpenAiName
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

// Deploy GPT-4o-mini for reasoning, entity extraction, and interview rubrics
resource gpt4oMiniDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = if (deployGpt4oMini) {
  parent: openAiAccount
  name: 'gpt-4o-mini'
  sku: {
    name: 'Standard'
    capacity: 30
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o-mini'
      version: '2024-07-18'
    }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
    raiPolicyName: 'Microsoft.Default'
  }
}

// Deploy text-embedding-3-small for semantic vector similarity
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = if (deployEmbedding) {
  parent: openAiAccount
  name: 'text-embedding-3-small'
  sku: {
    name: 'Standard'
    capacity: 20
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-small'
      version: '1'
    }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
    raiPolicyName: 'Microsoft.Default'
  }
  dependsOn: [
    gpt4oMiniDeployment
  ]
}

var openAiKeys = openAiAccount.listKeys()

output openAiId string = openAiAccount.id
output openAiName string = openAiAccount.name
output endpoint string = openAiAccount.properties.endpoint
output apiKey string = openAiKeys.key1
output gptDeploymentName string = 'gpt-4o-mini'
output embeddingDeploymentName string = 'text-embedding-3-small'
output apiVersion string = '2024-08-01-preview'
