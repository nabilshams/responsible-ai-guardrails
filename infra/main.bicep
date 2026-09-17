// Main Bicep template for Responsible AI Guardrails - Microsoft Foundry hosted agent solution
// Supports public networking or private networking with VNet injection and private endpoints.

targetScope = 'resourceGroup'

// ========== PARAMETERS ==========

@minLength(1)
@maxLength(20)
@description('Primary identifier prefix for all resources')
param environmentName string

@description('Primary Azure region for resources')
param location string = resourceGroup().location

@description('Deploy with VNet injection, private endpoints, and private DNS. Set to false for public networking.')
param useVnet bool = true

@description('VNet address space (CIDR)')
param vnetAddressPrefix string = '10.40.0.0/16'

@description('Agent subnet address range (delegated to Microsoft.App/environments)')
param agentSubnetPrefix string = '10.40.0.0/24'

@description('Private endpoint subnet address range')
param privateEndpointSubnetPrefix string = '10.40.1.0/24'

@allowed([
  'F0'
  'S'
])
@description('Azure AI Language SKU. F0 is the lowest tier; use S when free-tier limits are unsuitable or F0 is unavailable in the subscription/region.')
param aiLanguageSku string = 'F0'

@allowed([
  'F0'
  'S0'
])
@description('Azure Document Intelligence SKU. F0 is for development; use S0 for production documents.')
param docIntelligenceSku string = 'F0'

@description('Minimum confidence required to redact a detected PII entity.')
param piiConfidenceThreshold string = '0.7'

@minLength(2)
@maxLength(12)
@description('Default language code used for PII detection.')
param piiDefaultLanguage string = 'en'

// ========== VARIABLES ==========

var tags = {
  azdEnvName: environmentName
  solution: 'responsible-ai-guardrails'
}

var abbrs = loadJsonContent('./abbreviations.json')
var uniqueSuffix = uniqueString(subscription().id, resourceGroup().id, environmentName)
var normalizedEnvironmentName = toLower(replace(environmentName, '-', ''))

// Azure naming conventions (max lengths from https://learn.microsoft.com/azure/azure-resource-manager/management/resource-name-rules)
var resourceNames = {
  vnet: '${abbrs.networkVirtualNetworks}${environmentName}'
  agentSubnet: 'snet-agent'
  peSubnet: 'snet-pe'
  nsgAgent: '${abbrs.networkNetworkSecurityGroups}agent-${environmentName}'
  nsgPe: '${abbrs.networkNetworkSecurityGroups}pe-${environmentName}'
  acr: take('cr${normalizedEnvironmentName}${uniqueSuffix}', 50)
  aiServices: take('${abbrs.cognitiveServicesAccounts}foundry-${environmentName}-${uniqueSuffix}', 64)
  aiProject: 'aiproj-${environmentName}'
  aiLanguage: take('${abbrs.cognitiveServicesAccounts}language-${environmentName}-${uniqueSuffix}', 64)
  docIntelligence: take('${abbrs.cognitiveServicesAccounts}docintel-${environmentName}-${uniqueSuffix}', 64)
  documentStorage: take('st${normalizedEnvironmentName}${uniqueSuffix}', 24)
  logAnalytics: '${abbrs.operationalInsightsWorkspaces}${environmentName}'
  appInsights: '${abbrs.insightsComponents}${environmentName}'
  ampls: 'ampls-${environmentName}'
}

// ========== MODULES ==========

// Network infrastructure (VNet, subnets, NSGs)
module network 'modules/network.bicep' = if (useVnet) {
  name: 'network-deployment'
  params: {
    location: location
    tags: tags
    vnetName: resourceNames.vnet
    vnetAddressPrefix: vnetAddressPrefix
    agentSubnetName: resourceNames.agentSubnet
    agentSubnetPrefix: agentSubnetPrefix
    peSubnetName: resourceNames.peSubnet
    peSubnetPrefix: privateEndpointSubnetPrefix
    nsgAgentName: resourceNames.nsgAgent
    nsgPeName: resourceNames.nsgPe
  }
}

// Monitoring infrastructure (Log Analytics, App Insights, Azure Monitor Private Link Scope)
module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring-deployment'
  params: {
    location: location
    tags: tags
    logAnalyticsName: resourceNames.logAnalytics
    appInsightsName: resourceNames.appInsights
    amplsName: resourceNames.ampls
    useVnet: useVnet
  }
}

// Private DNS zones for all private endpoint types
module dns 'modules/dns.bicep' = if (useVnet) {
  name: 'dns-deployment'
  params: {
    vnetId: network!.outputs.vnetId
    tags: tags
  }
}

// Azure Container Registry (Basic, public endpoint protected by Microsoft Entra RBAC)
module acr 'modules/acr.bicep' = {
  name: 'acr-deployment'
  params: {
    location: location
    tags: tags
    acrName: resourceNames.acr
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsId
  }
}

// Temporary source and target containers required by Azure AI Language document-based PII.
module documentStorage 'modules/documentStorage.bicep' = {
  name: 'document-storage-deployment'
  params: {
    location: location
    tags: tags
    storageAccountName: resourceNames.documentStorage
    useVnet: useVnet
  }
}

// Microsoft Foundry AI Services, Azure AI Language, and Document Intelligence
module ai 'modules/ai.bicep' = {
  name: 'ai-deployment'
  params: {
    location: location
    tags: tags
    aiServicesName: resourceNames.aiServices
    aiLanguageName: resourceNames.aiLanguage
    docIntelligenceName: resourceNames.docIntelligence
    aiLanguageSku: aiLanguageSku
    docIntelligenceSku: docIntelligenceSku
    useVnet: useVnet
    agentSubnetId: useVnet ? network!.outputs.agentSubnetId : ''
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsId
  }
}

// Register Application Insights with Foundry after both resources exist.
module foundryMonitoringConnection 'modules/foundryMonitoringConnection.bicep' = {
  name: 'foundry-monitoring-connection'
  params: {
    aiServicesName: ai.outputs.aiServicesName
    appInsightsId: monitoring.outputs.appInsightsId
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
  }
}

// Private endpoints for AI services and Azure Monitor; ACR intentionally uses its public endpoint
module privateEndpoints 'modules/privateEndpoints.bicep' = if (useVnet) {
  name: 'private-endpoints-deployment'
  params: {
    location: location
    tags: tags
    peSubnetId: network!.outputs.peSubnetId
    aiServicesId: ai.outputs.aiServicesId
    aiLanguageId: ai.outputs.aiLanguageId
    docIntelligenceId: ai.outputs.docIntelligenceId
    amplsId: monitoring.outputs.amplsId
    documentStorageId: documentStorage.outputs.storageAccountId
    // Private DNS zone IDs
    cognitiveServicesDnsZoneId: dns!.outputs.cognitiveServicesDnsZoneId
    openaiDnsZoneId: dns!.outputs.openaiDnsZoneId
    aiServicesDnsZoneId: dns!.outputs.aiServicesDnsZoneId
    monitorDnsZoneId: dns!.outputs.monitorDnsZoneId
    omsDnsZoneId: dns!.outputs.omsDnsZoneId
    odsDnsZoneId: dns!.outputs.odsDnsZoneId
    agentSvcDnsZoneId: dns!.outputs.agentSvcDnsZoneId
    blobDnsZoneId: dns!.outputs.blobDnsZoneId
  }
}

// In VNet mode, create the project only after private connectivity exists.
module foundryProject 'modules/foundryProject.bicep' = {
  name: 'foundry-project-deployment'
  params: {
    location: location
    aiServicesName: ai.outputs.aiServicesName
    aiProjectName: resourceNames.aiProject
    useVnet: useVnet
  }
  dependsOn: [
    privateEndpoints
  ]
}

// RBAC assignments (ACR pull access for AI Services system identity)
module rbac 'modules/rbac.bicep' = {
  name: 'rbac-deployment'
  params: {
    acrId: acr.outputs.acrId
    projectPrincipalId: foundryProject.outputs.aiProjectPrincipalId
    documentStorageId: documentStorage.outputs.storageAccountId
    aiLanguagePrincipalId: ai.outputs.aiLanguageSystemPrincipalId
  }
}

// ========== OUTPUTS (azd environment variables) ==========

// Deployment context and selected options
output AZURE_ENV_NAME string = environmentName
output AZURE_LOCATION string = location
output AZURE_SUBSCRIPTION_ID string = subscription().subscriptionId
output AZURE_TENANT_ID string = tenant().tenantId
output USE_VNET string = string(useVnet)
output VNET_ADDRESS_PREFIX string = vnetAddressPrefix
output AGENT_SUBNET_PREFIX string = agentSubnetPrefix
output PE_SUBNET_PREFIX string = privateEndpointSubnetPrefix
output AI_LANGUAGE_SKU string = aiLanguageSku
output DOCUMENT_INTELLIGENCE_SKU string = docIntelligenceSku

// AI Services endpoints
output FOUNDRY_PROJECT_ENDPOINT string = foundryProject.outputs.aiProjectEndpoint
output AZURE_AI_PROJECT_ENDPOINT string = foundryProject.outputs.aiProjectEndpoint
output AZURE_AIPROJECT_ENDPOINT string = foundryProject.outputs.aiProjectEndpoint
output AZURE_AI_PROJECT_ID string = foundryProject.outputs.aiProjectId
output AZURE_AI_PROJECT_NAME string = foundryProject.outputs.aiProjectName
output AZURE_AI_ACCOUNT_NAME string = ai.outputs.aiServicesName
output AZURE_AI_AISERVICES_ACCOUNT_NAME string = ai.outputs.aiServicesName
output AZURE_AI_LANGUAGE_ENDPOINT string = ai.outputs.aiLanguageEndpoint
output AZURE_AI_LANGUAGE_RESOURCE_ID string = ai.outputs.aiLanguageId
output AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT string = ai.outputs.docIntelligenceEndpoint
output AZURE_DOCUMENT_INTELLIGENCE_RESOURCE_ID string = ai.outputs.docIntelligenceId
output AZURE_DOCUMENT_PII_STORAGE_ENDPOINT string = documentStorage.outputs.blobEndpoint
output AZURE_DOCUMENT_PII_STORAGE_RESOURCE_ID string = documentStorage.outputs.storageAccountId
output AZURE_DOCUMENT_PII_SOURCE_CONTAINER string = documentStorage.outputs.sourceContainerName
output AZURE_DOCUMENT_PII_TARGET_CONTAINER string = documentStorage.outputs.targetContainerName

// Container registry
output AZURE_CONTAINER_REGISTRY_RESOURCE_ID string = acr.outputs.acrId
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = acr.outputs.acrLoginServer
output AZURE_CONTAINER_REGISTRY_NAME string = acr.outputs.acrName

// Monitoring
output APPLICATIONINSIGHTS_CONNECTION_STRING string = monitoring.outputs.appInsightsConnectionString
output AZURE_LOG_ANALYTICS_WORKSPACE_ID string = monitoring.outputs.logAnalyticsId

// Network
output VNET_ID string = useVnet ? network!.outputs.vnetId : ''
output AGENT_SUBNET_ID string = useVnet ? network!.outputs.agentSubnetId : ''
output PE_SUBNET_ID string = useVnet ? network!.outputs.peSubnetId : ''
output AZURE_RESOURCE_GROUP string = resourceGroup().name

// Environment config (agent configuration values)
output ENABLE_CAPABILITY_HOST string = 'true'
output PII_CONFIDENCE_THRESHOLD string = piiConfidenceThreshold
output PII_DEFAULT_LANGUAGE string = piiDefaultLanguage
