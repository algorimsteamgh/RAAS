@description('Azure Region for Container Registry')
param location string

@description('Environment prefix, e.g. dev, staging, prod')
param environment string

@description('Application name prefix')
param appName string

@description('SKU for Azure Container Registry')
@allowed([
  'Basic'
  'Standard'
  'Premium'
])
param acrSku string = 'Basic'

var acrName = 'cr${replace(appName, '-', '')}${environment}${uniqueString(resourceGroup().id)}'
var cleanAcrName = take(toLower(acrName), 50)

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: cleanAcrName
  location: location
  sku: {
    name: acrSku
  }
  properties: {
    adminUserEnabled: true
    publicNetworkAccess: 'Enabled'
    zoneRedundancy: 'Disabled'
  }
}

var credentials = containerRegistry.listCredentials()

output acrId string = containerRegistry.id
output acrName string = containerRegistry.name
output loginServer string = containerRegistry.properties.loginServer
output adminUsername string = credentials.username
output adminPassword string = credentials.passwords[0].value
