targetScope = 'resourceGroup'

@minLength(1)
@maxLength(20)
param environmentName string

param location string = resourceGroup().location
param aiLanguageSku string = 'S'
param docIntelligenceSku string = 'S0'
param piiConfidenceThreshold string = '0.7'
param piiDefaultLanguage string = 'en'

module solution '../main.bicep' = {
  params: {
    environmentName: environmentName
    location: location
    useVnet: false
    allowPublicFoundryAccess: true
    aiLanguageSku: aiLanguageSku
    docIntelligenceSku: docIntelligenceSku
    piiConfidenceThreshold: piiConfidenceThreshold
    piiDefaultLanguage: piiDefaultLanguage
  }
}

output AZURE_ENV_NAME string = solution.outputs.AZURE_ENV_NAME
output AZURE_LOCATION string = solution.outputs.AZURE_LOCATION
output AZURE_SUBSCRIPTION_ID string = solution.outputs.AZURE_SUBSCRIPTION_ID
output AZURE_TENANT_ID string = solution.outputs.AZURE_TENANT_ID
output USE_VNET string = solution.outputs.USE_VNET
output ALLOW_PUBLIC_FOUNDRY_ACCESS string = solution.outputs.ALLOW_PUBLIC_FOUNDRY_ACCESS
output VNET_ADDRESS_PREFIX string = solution.outputs.VNET_ADDRESS_PREFIX
output AGENT_SUBNET_PREFIX string = solution.outputs.AGENT_SUBNET_PREFIX
output PE_SUBNET_PREFIX string = solution.outputs.PE_SUBNET_PREFIX
output WEB_SUBNET_PREFIX string = solution.outputs.WEB_SUBNET_PREFIX
output AI_LANGUAGE_SKU string = solution.outputs.AI_LANGUAGE_SKU
output DOCUMENT_INTELLIGENCE_SKU string = solution.outputs.DOCUMENT_INTELLIGENCE_SKU
output FOUNDRY_PROJECT_ENDPOINT string = solution.outputs.FOUNDRY_PROJECT_ENDPOINT
output AZURE_AI_PROJECT_ENDPOINT string = solution.outputs.AZURE_AI_PROJECT_ENDPOINT
output AZURE_AIPROJECT_ENDPOINT string = solution.outputs.AZURE_AIPROJECT_ENDPOINT
output AZURE_AI_PROJECT_ID string = solution.outputs.AZURE_AI_PROJECT_ID
output AZURE_AI_PROJECT_NAME string = solution.outputs.AZURE_AI_PROJECT_NAME
output AZURE_AI_ACCOUNT_NAME string = solution.outputs.AZURE_AI_ACCOUNT_NAME
output AZURE_AI_AISERVICES_ACCOUNT_NAME string = solution.outputs.AZURE_AI_AISERVICES_ACCOUNT_NAME
output AZURE_AI_LANGUAGE_ENDPOINT string = solution.outputs.AZURE_AI_LANGUAGE_ENDPOINT
output AZURE_AI_LANGUAGE_RESOURCE_ID string = solution.outputs.AZURE_AI_LANGUAGE_RESOURCE_ID
output AZURE_SPEECH_ENDPOINT string = solution.outputs.AZURE_SPEECH_ENDPOINT
output AZURE_SPEECH_RESOURCE_ID string = solution.outputs.AZURE_SPEECH_RESOURCE_ID
output AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT string = solution.outputs.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT
output AZURE_DOCUMENT_INTELLIGENCE_RESOURCE_ID string = solution.outputs.AZURE_DOCUMENT_INTELLIGENCE_RESOURCE_ID
output AZURE_DOCUMENT_PII_STORAGE_ENDPOINT string = solution.outputs.AZURE_DOCUMENT_PII_STORAGE_ENDPOINT
output AZURE_DOCUMENT_PII_STORAGE_RESOURCE_ID string = solution.outputs.AZURE_DOCUMENT_PII_STORAGE_RESOURCE_ID
output AZURE_DOCUMENT_PII_SOURCE_CONTAINER string = solution.outputs.AZURE_DOCUMENT_PII_SOURCE_CONTAINER
output AZURE_DOCUMENT_PII_TARGET_CONTAINER string = solution.outputs.AZURE_DOCUMENT_PII_TARGET_CONTAINER
output AZURE_CONTAINER_REGISTRY_RESOURCE_ID string = solution.outputs.AZURE_CONTAINER_REGISTRY_RESOURCE_ID
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = solution.outputs.AZURE_CONTAINER_REGISTRY_ENDPOINT
output AZURE_CONTAINER_REGISTRY_NAME string = solution.outputs.AZURE_CONTAINER_REGISTRY_NAME
output AZURE_REDACTION_CHAT_NAME string = solution.outputs.AZURE_REDACTION_CHAT_NAME
output AZURE_REDACTION_CHAT_PRINCIPAL_ID string = solution.outputs.AZURE_REDACTION_CHAT_PRINCIPAL_ID
output AZURE_REDACTION_CHAT_URL string = solution.outputs.AZURE_REDACTION_CHAT_URL
output AZURE_CONTAINER_APPS_ENVIRONMENT_NAME string = solution.outputs.AZURE_CONTAINER_APPS_ENVIRONMENT_NAME
output APPLICATIONINSIGHTS_CONNECTION_STRING string = solution.outputs.APPLICATIONINSIGHTS_CONNECTION_STRING
output AZURE_LOG_ANALYTICS_WORKSPACE_ID string = solution.outputs.AZURE_LOG_ANALYTICS_WORKSPACE_ID
output VNET_ID string = solution.outputs.VNET_ID
output AGENT_SUBNET_ID string = solution.outputs.AGENT_SUBNET_ID
output PE_SUBNET_ID string = solution.outputs.PE_SUBNET_ID
output WEB_SUBNET_ID string = solution.outputs.WEB_SUBNET_ID
output AZURE_RESOURCE_GROUP string = solution.outputs.AZURE_RESOURCE_GROUP
output ENABLE_CAPABILITY_HOST string = solution.outputs.ENABLE_CAPABILITY_HOST
output PII_CONFIDENCE_THRESHOLD string = solution.outputs.PII_CONFIDENCE_THRESHOLD
output PII_DEFAULT_LANGUAGE string = solution.outputs.PII_DEFAULT_LANGUAGE
