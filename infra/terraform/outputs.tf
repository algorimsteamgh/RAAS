output "application_url" {
  description = "Public URL of Frontend Web Application"
  value       = "https://${azurerm_container_app.frontend.ingress[0].fqdn}"
}

output "backend_api_url" {
  description = "URL of Backend FastAPI Application"
  value       = "https://${azurerm_container_app.backend.ingress[0].fqdn}"
}

output "acr_login_server" {
  description = "Azure Container Registry Login Server"
  value       = azurerm_container_registry.acr.login_server
}

output "storage_account_name" {
  description = "Azure Storage Account Name"
  value       = azurerm_storage_account.sa.name
}

output "openai_endpoint" {
  description = "Azure OpenAI Service Endpoint"
  value       = var.deploy_azure_openai ? azurerm_cognitive_account.openai[0].endpoint : var.existing_openai_endpoint
}
