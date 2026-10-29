terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }
}

provider "azurerm" {
  features {}
}

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

locals {
  name_prefix = "${var.app_name}-${var.environment}-${random_string.suffix.result}"
}

# Resource Group
resource "azurerm_resource_group" "rg" {
  name     = "rg-${local.name_prefix}"
  location = var.location
  tags = {
    Environment = var.environment
    Project     = "CVScreening-FDE"
    ManagedBy   = "Terraform"
  }
}

# Log Analytics Workspace & Application Insights
resource "azurerm_log_analytics_workspace" "law" {
  name                = "law-${local.name_prefix}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_application_insights" "appi" {
  name                = "appi-${local.name_prefix}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.law.id
}

# Azure Container Registry
resource "azurerm_container_registry" "acr" {
  name                = "cr${replace(var.app_name, "-", "")}${var.environment}${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "Standard"
  admin_enabled       = true
}

# Storage Account & Blob Containers & File Share for persistent DB
resource "azurerm_storage_account" "sa" {
  name                     = "st${replace(var.app_name, "-", "")}${var.environment}${random_string.suffix.result}"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
}

resource "azurerm_storage_container" "resumes" {
  name                  = "cv-resumes"
  storage_account_id    = azurerm_storage_account.sa.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "extracted" {
  name                  = "cv-extracted"
  storage_account_id    = azurerm_storage_account.sa.id
  container_access_type = "private"
}

resource "azurerm_storage_share" "data_share" {
  name               = "cv-data"
  storage_account_id = azurerm_storage_account.sa.id
  quota              = 50
}

# Azure OpenAI Service (Conditional)
resource "azurerm_cognitive_account" "openai" {
  count                 = var.deploy_azure_openai ? 1 : 0
  name                  = "oai-${local.name_prefix}"
  location              = azurerm_resource_group.rg.location
  resource_group_name   = azurerm_resource_group.rg.name
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = "oai-${local.name_prefix}"
}

resource "azurerm_cognitive_deployment" "gpt4o_mini" {
  count                = var.deploy_azure_openai ? 1 : 0
  name                 = "gpt-4o-mini"
  cognitive_account_id = azurerm_cognitive_account.openai[0].id
  model {
    format  = "OpenAI"
    name    = "gpt-4o-mini"
    version = "2024-07-18"
  }
  sku {
    name     = "Standard"
    capacity = 30
  }
}

# Azure Container Apps Environment
resource "azurerm_container_app_environment" "cae" {
  name                       = "cae-${local.name_prefix}"
  location                   = azurerm_resource_group.rg.location
  resource_group_name        = azurerm_resource_group.rg.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id
}

# Azure Container App - Backend
resource "azurerm_container_app" "backend" {
  name                         = "app-${var.app_name}-backend-${var.environment}"
  container_app_environment_id = azurerm_container_app_environment.cae.id
  resource_group_name          = azurerm_resource_group.rg.name
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.acr.login_server
    username             = azurerm_container_registry.acr.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.acr.admin_password
  }

  secret {
    name  = "storage-conn-string"
    value = azurerm_storage_account.sa.primary_connection_string
  }

  secret {
    name  = "openai-api-key"
    value = var.deploy_azure_openai ? azurerm_cognitive_account.openai[0].primary_access_key : (var.existing_openai_api_key != "" ? var.existing_openai_api_key : "disabled")
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = 1
    max_replicas = 10

    container {
      name   = "backend"
      image  = "${azurerm_container_registry.acr.login_server}/cvscreening-backend:latest"
      cpu    = 1.0
      memory = "2Gi"

      env {
        name  = "ENVIRONMENT"
        value = "production"
      }
      env {
        name  = "PORT"
        value = "8000"
      }
      env {
        name  = "DATABASE_PATH"
        value = "/app/data/cv_screening.db"
      }
      env {
        name  = "MODEL_BACKEND"
        value = var.deploy_azure_openai ? "azure_openai" : "vllm"
      }
      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = var.deploy_azure_openai ? azurerm_cognitive_account.openai[0].endpoint : var.existing_openai_endpoint
      }
      env {
        name        = "AZURE_OPENAI_API_KEY"
        secret_name = "openai-api-key"
      }
      env {
        name  = "AZURE_OPENAI_DEPLOYMENT_NAME"
        value = "gpt-4o-mini"
      }
      env {
        name  = "AZURE_OPENAI_API_VERSION"
        value = "2024-08-01-preview"
      }
      env {
        name        = "AZURE_STORAGE_CONNECTION_STRING"
        secret_name = "storage-conn-string"
      }
      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.appi.connection_string
      }

      liveness_probe {
        port                    = 8000
        transport               = "HTTP"
        path                    = "/healthz"
        initial_delay           = 10
        interval_seconds        = 30
        failure_count_threshold = 3
      }

      readiness_probe {
        port                    = 8000
        transport               = "HTTP"
        path                    = "/readyz"
        initial_delay           = 5
        interval_seconds        = 15
        failure_count_threshold = 3
      }
    }
  }
}

# Azure Container App - Frontend
resource "azurerm_container_app" "frontend" {
  name                         = "app-${var.app_name}-frontend-${var.environment}"
  container_app_environment_id = azurerm_container_app_environment.cae.id
  resource_group_name          = azurerm_resource_group.rg.name
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.acr.login_server
    username             = azurerm_container_registry.acr.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.acr.admin_password
  }

  ingress {
    external_enabled = true
    target_port      = 80
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = 1
    max_replicas = 5

    container {
      name   = "frontend"
      image  = "${azurerm_container_registry.acr.login_server}/cvscreening-frontend:latest"
      cpu    = 0.5
      memory = "1Gi"

      liveness_probe {
        port             = 80
        transport        = "HTTP"
        path             = "/healthz"
        initial_delay    = 5
        interval_seconds = 30
      }
    }
  }
}
