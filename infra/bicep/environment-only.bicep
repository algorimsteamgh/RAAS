targetScope = 'resourceGroup'

@description('Azure Region for Container Apps Managed Environment')
param location string = 'eastus2'

@description('Deployment Environment')
@allowed([
  'dev'
  'staging'
  'prod'
])
param environment string = 'prod'

@description('Application Name prefix')
param appName string = 'cvscreen'

// Reference existing Log Analytics Workspace in eastus
var logAnalyticsWorkspaceName = 'law-${appName}-${environment}-${uniqueString(resourceGroup().id)}'

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = {
  name: logAnalyticsWorkspaceName
}

var environmentName = 'cae-${appName}-${environment}-${location}-${uniqueString(resourceGroup().id)}'

// Azure Container Apps Managed Environment in eastus2
resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspace.properties.customerId
        sharedKey: logAnalyticsWorkspace.listKeys().primarySharedKey
      }
    }
    zoneRedundant: false
  }
}

output environmentId string = managedEnvironment.id
output environmentName string = managedEnvironment.name
output defaultDomain string = managedEnvironment.properties.defaultDomain
output location string = managedEnvironment.location
output staticIp string = managedEnvironment.properties.staticIp
