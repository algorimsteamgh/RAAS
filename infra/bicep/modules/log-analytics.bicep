@description('Azure Region for Log Analytics and Application Insights')
param location string

@description('Environment prefix, e.g. dev, staging, prod')
param environment string

@description('Application name prefix')
param appName string

var logAnalyticsWorkspaceName = 'law-${appName}-${environment}-${uniqueString(resourceGroup().id)}'
var appInsightsName = 'appi-${appName}-${environment}-${uniqueString(resourceGroup().id)}'

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsWorkspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    features: {
      searchVersion: 1
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspace.id
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

output logAnalyticsId string = logAnalyticsWorkspace.id
output logAnalyticsCustomerId string = logAnalyticsWorkspace.properties.customerId
output logAnalyticsSharedKey string = logAnalyticsWorkspace.listKeys().primarySharedKey
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output appInsightsInstrumentationKey string = appInsights.properties.InstrumentationKey
