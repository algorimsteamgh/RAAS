variable "location" {
  description = "Azure Region"
  type        = string
  default     = "eastus"
}

variable "environment" {
  description = "Environment name (e.g. dev, prod)"
  type        = string
  default     = "prod"
}

variable "app_name" {
  description = "Application name prefix"
  type        = string
  default     = "cvscreen"
}

variable "deploy_azure_openai" {
  description = "Whether to provision Azure OpenAI"
  type        = bool
  default     = true
}

variable "existing_openai_endpoint" {
  description = "Existing Azure OpenAI endpoint if deploy_azure_openai is false"
  type        = string
  default     = ""
}

variable "existing_openai_api_key" {
  description = "Existing Azure OpenAI API key if deploy_azure_openai is false"
  type        = string
  default     = ""
  sensitive   = true
}
