# Phase 13 — CVScreen Gate 3 Infrastructure Provisioning Report

**Document:** `PHASE13_INFRASTRUCTURE_PROVISIONING_REPORT.md`  
**Role:** Senior Azure Cloud Architect & DevOps Engineer  
**Date:** October 16, 2026  
**Status:** Preflight Halted — Hard Azure Subscription Quota Limit Identified  
**Target Resource Group:** `rg-cvscreening-prod`  
**Target Environment:** `cae-cvscreen-prod-eastus2-example` (`eastus2`)  
**Scope:** Environment-Only Provisioning (Zero Application Containers, Zero Image Pushes)  

---

## 1. Executive Summary & Critical Stop-Condition Trigger

During the mandatory Step 3 preflight validation for Gate 3 environment-only provisioning, Azure Resource Manager rejected the creation of the new Container Apps Managed Environment with an explicit, hard quota error:

```json
{
  "code": "InvalidTemplateDeployment",
  "message": "The template deployment 'environment-only' is not valid according to the validation procedure. The following resource provider(s) - 'Microsoft.App/managedEnvironments (2024-03-01)' reported preflight validation errors. Tracking id is '0e986a8c-f6cd-4efb-a39e-52d55889167b'. See inner errors for details."
}
Inner Errors:
{
  "code": "MaxNumberOfGlobalEnvironmentsInSubExceeded",
  "message": "The subscription cannot have more than 1 Container App Environments. For more information, visit: https://go.microsoft.com/fwlink/?linkid=2208872"
}
```

### Root Cause Analysis
1. **Azure Free Trial Quota Policy:** Under the Azure Free Trial policy (`quotaId: "FreeTrial_2014-09-01"`), Azure strictly limits each subscription to a maximum of **1 Container App Environment globally** across all regions and resource groups.
2. **Current Subscription State:** There is already **1** Container App Environment in the subscription: `cae-cvscreen-prod-example` in `rg-cvscreening-prod` (located in `eastus`, currently in `Failed` state due to the earlier regional capacity constraint).
3. **Quota Consumption:** Even though `cae-cvscreen-prod-example` is in a `Failed` state and hosts 0 container apps, the Azure Resource Provider counts it as 1 of 1 allocated environments.
4. **Enforcement of Mandatory Stop Condition:**  
   The user's instructions for Gate 3 explicitly mandate:
   - *"Do not delete or modify the failed eastus environment."*
   - *"If any check fails, or if the deployment scope is ambiguous, stop without provisioning."*
   - *"If Azure reports a capacity, quota, naming, networking, or provisioning error, stop and report it. Do not retry in another region or create alternative resources automatically."*
   
   In strict compliance with these instructions, **no provisioning was executed, no resources were modified, and the operation was stopped immediately**.

---

## 2. Strict Safety & Compliance Attestation

- **Azure Resources Mutated:** **0** (No resources created, scaled, modified, or deleted).
- **Application Containers Deployed:** **0** (Neither frontend nor backend Container Apps were deployed).
- **Images Pushed:** **0** (No new images pushed during this phase).
- **Live Smoke Tests:** **0** (No network traffic dispatched to production).
- **Failed `eastus` Environment:** **Untouched** (Remains in `rg-cvscreening-prod` in `Failed` state).
- **Base `eastus` Resources:** **Untouched** (Storage, ACR, and Monitoring preserved intact).

---

## 3. The Prepared Environment-Only Bicep Template

In accordance with Step 2, a minimal, isolated Bicep template was authored at [`infra/bicep/environment-only.bicep`](file:///Users/apple/cvscreening/infra/bicep/environment-only.bicep):

```bicep
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
```

### Scope Verification:
- **Zero Container Apps:** Does not contain or deploy `app-cvscreen-backend-prod` or `app-cvscreen-frontend-prod`.
- **Zero Storage / ACR Creation:** Only declares the single `managedEnvironment` resource and references the existing Log Analytics Workspace.
- **Zero Secret Outputs:** Outputs contain only IDs, names, domain, location, and static IP.

---

## 4. Preflight & Validation Results

### 4.1. Local Bicep Compilation
```bash
az bicep build --file infra/bicep/environment-only.bicep --outfile /dev/null
```
- **Exit Code:** `0`
- **Result:** Clean compilation. Zero syntax errors, zero linter warnings.

### 4.2. Target Environment Existence Check
```bash
az resource list --resource-group rg-cvscreening-prod --name "cae-cvscreen-prod-eastus2-example"
```
- **Result:** Resource does not exist. No naming collision in `eastus2`.

### 4.3. ARM Pre-Flight Validation
```bash
az deployment group validate \
  --resource-group rg-cvscreening-prod \
  --template-file infra/bicep/environment-only.bicep
```
- **Exit Code:** `1` (Failed)
- **Error Code:** `MaxNumberOfGlobalEnvironmentsInSubExceeded`
- **Error Message:** `The subscription cannot have more than 1 Container App Environments.`

---

## 5. Subscription Environment Inventory

A complete audit of all Container App Environments in the subscription confirmed:

```json
[
  {
    "location": "East US",
    "name": "cae-cvscreen-prod-example",
    "provisioningState": "Failed",
    "resourceGroup": "rg-cvscreening-prod"
  }
]
```

- **Total Environments in Subscription:** `1`
- **Subscription Quota Limit:** `1`
- **Available Environment Slots:** `0`

---

## 6. The Architectural Decision for User Approval

Because of the hard platform quota limit of 1 Container App Environment on Azure Free Trial subscriptions, there is exactly one clean path to deploy the working environment in `eastus2`:

### The Required Action:
Delete the failed, dead environment `cae-cvscreen-prod-example` in `eastus`:
```bash
az containerapp env delete \
  --name cae-cvscreen-prod-example \
  --resource-group rg-cvscreening-prod \
  --yes
```

### Safety & Impact of Deleting the Failed Environment:
1. **Contains Zero Containers:** No applications are running in it (`az containerapp list` is empty).
2. **Permanently Unusable:** It is stuck in `provisioningState: Failed` due to the East US capacity exhaustion.
3. **Does Not Affect Base Resources:** Deleting this environment does **not** affect your Storage Account, Azure Files shares, Container Registry, images, Log Analytics, or Application Insights in `eastus`.
4. **Frees the Global Quota:** Deleting it reduces the subscription environment count from `1` to `0`, immediately allowing `cae-cvscreen-prod-eastus2-example` to be created in `eastus2`.

---

## 7. Approval Request

In strict compliance with the Phase 13 instructions, I have halted execution. To proceed, please explicitly confirm if you authorize:

- [ ] **Approval to delete the failed `eastus` environment** (`cae-cvscreen-prod-example`) to free the single subscription quota slot.
- [ ] **Approval to deploy `environment-only.bicep`** in `eastus2` immediately after deletion.

Awaiting your explicit instructions.
