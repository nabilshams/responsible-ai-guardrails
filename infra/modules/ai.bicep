// Microsoft Foundry AI Services and supporting Cognitive Services resources
// All use system identity and derive their network access from the selected deployment mode.

targetScope = 'resourceGroup'

param location string
param tags object
param aiServicesName string
param aiLanguageName string
param speechName string
param docIntelligenceName string
param aiLanguageSku string
param docIntelligenceSku string
param useVnet bool
param allowPublicFoundryAccess bool
param agentSubnetId string
param logAnalyticsWorkspaceId string

var publicNetworkAccess = useVnet ? 'Disabled' : 'Enabled'
var networkDefaultAction = useVnet ? 'Deny' : 'Allow'
var foundryPublicNetworkAccess = (!useVnet || allowPublicFoundryAccess) ? 'Enabled' : 'Disabled'
var foundryNetworkDefaultAction = (!useVnet || allowPublicFoundryAccess) ? 'Allow' : 'Deny'

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
  properties: union({
    allowProjectManagement: true
    customSubDomainName: aiServicesName
    publicNetworkAccess: foundryPublicNetworkAccess
    networkAcls: {
      defaultAction: foundryNetworkDefaultAction
      bypass: 'AzureServices'
      ipRules: []
      virtualNetworkRules: []
    }
    disableLocalAuth: true
  }, useVnet ? {
    networkInjections: [
      {
        scenario: 'agent'
        subnetArmId: agentSubnetId
        useMicrosoftManagedNetwork: false
      }
    ]
  } : {})
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
    publicNetworkAccess: publicNetworkAccess
    networkAcls: {
      defaultAction: networkDefaultAction
      ipRules: []
      virtualNetworkRules: []
    }
    disableLocalAuth: true // Managed identity only
  }
}

// Azure AI Speech for demo narration
resource speech 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: speechName
  location: location
  tags: tags
  kind: 'SpeechServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: speechName
    publicNetworkAccess: publicNetworkAccess
    networkAcls: {
      defaultAction: networkDefaultAction
      ipRules: []
      virtualNetworkRules: []
    }
    disableLocalAuth: true
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
    publicNetworkAccess: publicNetworkAccess
    networkAcls: {
      defaultAction: networkDefaultAction
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
output speechId string = speech.id
output speechName string = speech.name
output speechEndpoint string = speech.properties.endpoint
output docIntelligenceId string = docIntelligence.id
output docIntelligenceName string = docIntelligence.name
output docIntelligenceEndpoint string = docIntelligence.properties.endpoint
