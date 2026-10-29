@description('Azure Region')
param location string

@description('Environment prefix, e.g. dev, staging, prod')
param environment string

@description('Application name prefix')
param appName string

@description('Log Analytics Workspace ID')
param logAnalyticsWorkspaceId string

@description('Log Analytics Customer ID')
param logAnalyticsCustomerId string

@description('Log Analytics Primary Shared Key')
@secure()
param logAnalyticsSharedKey string

@description('Application Insights Connection String')
param appInsightsConnectionString string

@description('Azure Container Registry Login Server')
param acrLoginServer string

@description('Azure Container Registry Admin Username')
param acrUsername string

@description('Azure Container Registry Admin Password')
@secure()
param acrPassword string

@description('Backend Container Image (e.g. crxxx.azurecr.io/cvscreening-backend:latest)')
param backendImage string

@description('Frontend Container Image (e.g. crxxx.azurecr.io/cvscreening-frontend:latest)')
param frontendImage string

@description('Storage Account Name for Persistent Mount')
param storageAccountName string

@description('Storage Account Key for Persistent Mount')
@secure()
param storageAccountKey string

@description('Azure Files Share Name')
param fileShareName string

@description('Azure Storage Connection String for Blob Uploads')
@secure()
param storageConnectionString string

@description('Azure OpenAI Endpoint')
param azureOpenAiEndpoint string

@description('Azure OpenAI API Key')
@secure()
param azureOpenAiApiKey string

@description('Azure OpenAI Deployment Name')
param azureOpenAiDeploymentName string

@description('Azure OpenAI API Version')
param azureOpenAiApiVersion string

@description('Backend LLM Engine Selection (vllm | azure_openai | ollama)')
param modelBackend string = 'vllm'

@description('Internal vLLM Endpoint URL')
param vllmBaseUrl string = ''

var environmentName = 'cae-${appName}-${environment}-${location}-${uniqueString(resourceGroup().id)}'
var backendAppName = 'app-${appName}-backend-${environment}'
var frontendAppName = 'app-${appName}-frontend-${environment}'

// 1. Container Apps Managed Environment
resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
    zoneRedundant: false
  }
}

// 2. Persistent Storage Mount (Azure Files CIFS -> Container Apps Environment)
resource storageMount 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: managedEnvironment
  name: 'cvdatamount'
  properties: {
    azureFile: {
      accountName: storageAccountName
      accountKey: storageAccountKey
      shareName: fileShareName
      accessMode: 'ReadWrite'
    }
  }
}

// 3. Backend Container App (FastAPI)
resource backendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: backendAppName
  location: location
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      secrets: [
        {
          name: 'acr-password'
          value: acrPassword
        }
        {
          name: 'storage-conn-string'
          value: storageConnectionString
        }
        {
          name: 'openai-api-key'
          value: empty(azureOpenAiApiKey) ? 'not-configured' : azureOpenAiApiKey
        }
      ]
      registries: [
        {
          server: acrLoginServer
          username: acrUsername
          passwordSecretRef: 'acr-password'
        }
      ]
      ingress: {
        external: false
        targetPort: 8000
        transport: 'auto'
        allowInsecure: true
        corsPolicy: {
          allowedOrigins: ['*']
          allowedMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
          allowedHeaders: ['*']
        }
      }
    }
    template: {
      volumes: [
        {
          name: 'cv-storage-volume'
          storageType: 'AzureFile'
          storageName: storageMount.name
        }
      ]
      containers: [
        {
          name: 'backend'
          image: backendImage
          resources: {
            cpu: json('2.0')
            memory: '4.0Gi'
          }
          env: [
            {
              name: 'ENVIRONMENT'
              value: 'production'
            }
            {
              name: 'PORT'
              value: '8000'
            }
            {
              name: 'DATABASE_PATH'
              value: '/app/local_data/cv_screening.db'
            }
            {
              name: 'MODEL_BACKEND'
              value: modelBackend
            }
            {
              name: 'VLLM_BASE_URL'
              value: vllmBaseUrl
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: azureOpenAiEndpoint
            }
            {
              name: 'AZURE_OPENAI_API_KEY'
              secretRef: 'openai-api-key'
            }
            {
              name: 'AZURE_OPENAI_DEPLOYMENT_NAME'
              value: azureOpenAiDeploymentName
            }
            {
              name: 'AZURE_OPENAI_API_VERSION'
              value: azureOpenAiApiVersion
            }
            {
              name: 'AZURE_STORAGE_CONNECTION_STRING'
              secretRef: 'storage-conn-string'
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: appInsightsConnectionString
            }
          ]
          volumeMounts: [
            {
              volumeName: 'cv-storage-volume'
              mountPath: '/app/data'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/api/system/health'
                port: 8000
              }
              initialDelaySeconds: 20
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 5
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/api/system/health'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 15
              timeoutSeconds: 5
              failureThreshold: 5
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
        rules: [
          {
            name: 'http-scaling-rule'
            http: {
              metadata: {
                concurrentRequests: '100'
              }
            }
          }
        ]
      }
    }
  }
}

// 4. Frontend Container App (React 19 / Nginx)
resource frontendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: frontendAppName
  location: location
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      secrets: [
        {
          name: 'acr-password'
          value: acrPassword
        }
      ]
      registries: [
        {
          server: acrLoginServer
          username: acrUsername
          passwordSecretRef: 'acr-password'
        }
      ]
      ingress: {
        external: true
        targetPort: 80
        transport: 'auto'
        allowInsecure: false
      }
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: frontendImage
          resources: {
            cpu: json('0.5')
            memory: '1.0Gi'
          }
          env: [
            {
              name: 'BACKEND_URL'
              value: 'http://${backendApp.properties.configuration.ingress.fqdn}'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: 80
              }
              initialDelaySeconds: 5
              periodSeconds: 30
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 5
        rules: [
          {
            name: 'http-scaling-rule'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
}

output environmentId string = managedEnvironment.id
output backendFqdn string = backendApp.properties.configuration.ingress.fqdn
output backendUrl string = 'https://${backendApp.properties.configuration.ingress.fqdn}'
output frontendFqdn string = frontendApp.properties.configuration.ingress.fqdn
output frontendUrl string = 'https://${frontendApp.properties.configuration.ingress.fqdn}'
