// Microsoft Foundry AI Services and supporting Cognitive Services resources
// All configured with system identity, private access only, no key-based auth where supported

targetScope = 'resourceGroup'

param location string
param tags object
param aiServicesName string
param aiLanguageName string
param docIntelligenceName string
param aiLanguageSku string
param docIntelligenceSku string
@allowed([
  'Enabled'
  'Disabled'
])
param foundryPublicNetworkAccess string
param agentSubnetId string
param logAnalyticsWorkspaceId string

// Microsoft Foundry AIServices account. Network injection must be configured
// when this account is first created; it cannot be added later for hosted agents.
#disable-next-line BCP081
resource aiServices 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: aiServicesName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: aiServicesName
    publicNetworkAccess: foundryPublicNetworkAccess
    networkAcls: {
      defaultAction: foundryPublicNetworkAccess == 'Enabled' ? 'Allow' : 'Deny'
      bypass: 'AzureServices'
      ipRules: []
      virtualNetworkRules: []
    }
    #disable-next-line BCP036
    networkInjections: [
      {
        scenario: 'agent'
        subnetArmId: agentSubnetId
        useMicrosoftManagedNetwork: false
      }
    ]
    disableLocalAuth: false // Foundry may require key auth for initial setup
  }
}

// Azure AI Language (PII detection and text analysis)
resource aiLanguage 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: aiLanguageName
  location: location
  tags: tags
  kind: 'TextAnalytics'
  sku: {
    name: aiLanguageSku
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: aiLanguageName
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
      ipRules: []
      virtualNetworkRules: []
    }
    disableLocalAuth: true // Managed identity only
  }
}

// Azure Document Intelligence (document extraction and OCR geometry)
resource docIntelligence 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: docIntelligenceName
  location: location
  tags: tags
  kind: 'FormRecognizer'
  sku: {
    name: docIntelligenceSku
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: docIntelligenceName
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
      ipRules: []
      virtualNetworkRules: []
    }
    disableLocalAuth: true
  }
}

// Diagnostic settings for AI Services
resource aiServicesDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'aiservices-diagnostics'
  scope: aiServices
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
    ]
  }
}

resource aiLanguageDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'ailanguage-diagnostics'
  scope: aiLanguage
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
    ]
  }
}

resource docIntelligenceDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'docintel-diagnostics'
  scope: docIntelligence
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
    ]
  }
}

output aiServicesId string = aiServices.id
output aiServicesName string = aiServices.name
output aiServicesEndpoint string = aiServices.properties.endpoint
output aiServicesSystemPrincipalId string = aiServices.identity.principalId
output aiLanguageId string = aiLanguage.id
output aiLanguageName string = aiLanguage.name
output aiLanguageEndpoint string = aiLanguage.properties.endpoint
output aiLanguageSystemPrincipalId string = aiLanguage.identity.principalId
output docIntelligenceId string = docIntelligence.id
output docIntelligenceName string = docIntelligence.name
output docIntelligenceEndpoint string = docIntelligence.properties.endpoint
