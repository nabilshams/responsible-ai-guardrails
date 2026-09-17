// Foundry project and Basic Agent capability hosts. VNet injection creates the
// account-level host automatically; public deployments create it explicitly.
targetScope = 'resourceGroup'

param location string
param aiServicesName string
param aiProjectName string
param useVnet bool

resource aiServices 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: aiServicesName
}

#disable-next-line BCP081
resource aiProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: aiServices
  name: aiProjectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: 'Responsible AI Guardrails'
    description: 'Private Microsoft Foundry project for deterministic Responsible AI guardrails.'
  }
}

#disable-next-line BCP081
resource accountCapabilityHost 'Microsoft.CognitiveServices/accounts/capabilityHosts@2025-04-01-preview' = if (!useVnet) {
  parent: aiServices
  name: '${aiServices.name}-capHost'
  properties: {
    #disable-next-line BCP037
    capabilityHostKind: 'Agents'
  }
}

#disable-next-line BCP081
resource projectCapabilityHost 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview' = {
  parent: aiProject
  name: 'caphostproj'
  properties: {
    #disable-next-line BCP037
    capabilityHostKind: 'Agents'
  }
  dependsOn: [
    accountCapabilityHost
  ]
}

output aiProjectName string = aiProject.name
output aiProjectId string = aiProject.id
output aiProjectPrincipalId string = aiProject.identity.principalId
output aiProjectEndpoint string = 'https://${aiServicesName}.services.ai.azure.com/api/projects/${aiProject.name}'
output capabilityHostName string = projectCapabilityHost.name
