// Shared Foundry connection used by hosted-agent OpenTelemetry integration.
targetScope = 'resourceGroup'

param aiServicesName string
param appInsightsId string
@secure()
param appInsightsConnectionString string

resource aiServices 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: aiServicesName
}

#disable-next-line BCP081
resource connection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  parent: aiServices
  name: '${aiServicesName}-appinsights'
  properties: {
    category: 'AppInsights'
    target: appInsightsId
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: appInsightsConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsightsId
    }
  }
}