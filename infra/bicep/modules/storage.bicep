@description('Azure Region for Storage Account')
param location string

@description('Environment prefix, e.g. dev, staging, prod')
param environment string

@description('Application name prefix')
param appName string

var storageAccountName = 'st${replace(appName, '-', '')}${environment}${uniqueString(resourceGroup().id)}'
var cleanStorageAccountName = take(toLower(storageAccountName), 24)

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: cleanStorageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    accessTier: 'Hot'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

// Blob Containers
resource blobServices 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 14
    }
  }
}

resource resumesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobServices
  name: 'cv-resumes'
  properties: {
    publicAccess: 'None'
  }
}

resource extractedContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobServices
  name: 'cv-extracted'
  properties: {
    publicAccess: 'None'
  }
}

// File Share for Persistent Container Apps Volume Mount (SQLite DB & Data files)
resource fileServices 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource cvDataShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileServices
  name: 'cv-data'
  properties: {
    shareQuota: 50
    enabledProtocols: 'SMB'
  }
}

// File Share for Fine-Tuned Model Weights (Qwen checkpoints / LoRA adapters)
resource cvModelsShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileServices
  name: 'cv-models'
  properties: {
    shareQuota: 100
    enabledProtocols: 'SMB'
  }
}

var storageKeys = storageAccount.listKeys().keys[0].value

output storageAccountId string = storageAccount.id
output storageAccountName string = storageAccount.name
output storageAccountKey string = storageKeys
output resumesContainerName string = resumesContainer.name
output extractedContainerName string = extractedContainer.name
output fileShareName string = cvDataShare.name
output modelsShareName string = cvModelsShare.name
output primaryBlobEndpoint string = storageAccount.properties.primaryEndpoints.blob
output connectionString string = 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageKeys};EndpointSuffix=${az.environment().suffixes.storage}'
