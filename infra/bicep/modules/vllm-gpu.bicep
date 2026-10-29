@description('Azure Region')
param location string

@description('Environment prefix, e.g. dev, staging, prod')
param environment string

@description('Application name prefix')
param appName string

@description('Container Apps Managed Environment ID')
param managedEnvironmentId string

@description('Azure Container Registry Login Server')
param acrLoginServer string

@description('Azure Container Registry Admin Username')
param acrUsername string

@description('Azure Container Registry Admin Password')
@secure()
param acrPassword string

@description('vLLM Container Image (e.g. crxxx.azurecr.io/cvscreening-vllm-qwen:latest)')
param vllmImage string

@description('Storage Mount Name for Models')
param modelStorageMountName string

@description('Model identifier to serve (default Qwen/Qwen2.5-7B-Instruct)')
param modelName string = 'Qwen/Qwen2.5-7B-Instruct'

var vllmAppName = 'app-${appName}-vllm-${environment}'

resource vllmApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: vllmAppName
  location: location
  properties: {
    managedEnvironmentId: managedEnvironmentId
    workloadProfileName: 'Consumption-GPU-NCasT4'
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
        external: false
        targetPort: 8000
        transport: 'auto'
        allowInsecure: true
      }
    }
    template: {
      volumes: [
        {
          name: 'models-volume'
          storageType: 'AzureFile'
          storageName: modelStorageMountName
        }
      ]
      containers: [
        {
          name: 'vllm-qwen'
          image: vllmImage
          resources: {
            cpu: json('4.0')
            memory: '16.0Gi'
          }
          env: [
            {
              name: 'MODEL_NAME'
              value: modelName
            }
            {
              name: 'MODEL_PATH'
              value: '/models/best_model'
            }
            {
              name: 'GPU_MEMORY_UTILIZATION'
              value: '0.90'
            }
            {
              name: 'MAX_MODEL_LEN'
              value: '8192'
            }
          ]
          volumeMounts: [
            {
              volumeName: 'models-volume'
              mountPath: '/models'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 60
              periodSeconds: 30
              failureThreshold: 5
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 30
              periodSeconds: 15
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-scaling-rule'
            http: {
              metadata: {
                concurrentRequests: '30'
              }
            }
          }
        ]
      }
    }
  }
}

output vllmFqdn string = vllmApp.properties.configuration.ingress.fqdn
output vllmInternalUrl string = 'http://${vllmApp.properties.configuration.ingress.fqdn}:8000/v1'
