// Foundry project and Basic Agent capability host. The parent account's
// network injection creates the account-level host; no BYO data stores exist.
targetScope = 'resourceGroup'

param location string
param aiServicesName string
param aiProjectName string

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
resource projectCapabilityHost 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview' = {
  parent: aiProject
  name: 'caphostproj'
  properties: {
    #disable-next-line BCP037
    capabilityHostKind: 'Agents'
  }
}

output aiProjectName string = aiProject.name
output aiProjectId string = aiProject.id
output aiProjectPrincipalId string = aiProject.identity.principalId
output aiProjectEndpoint string = 'https://${aiServicesName}.services.ai.azure.com/api/projects/${aiProject.name}'
output capabilityHostName string = projectCapabilityHost.name