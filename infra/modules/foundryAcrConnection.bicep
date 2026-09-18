targetScope = 'resourceGroup'

param aiServicesName string
param aiProjectName string
param acrName string
param acrEndpoint string
param acrResourceId string
param projectPrincipalId string

resource aiServices 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: aiServicesName

  resource project 'projects' existing = {
    name: aiProjectName

    resource acrConnection 'connections' = {
      name: '${acrName}-conn'
      properties: {
        category: 'ContainerRegistry'
        target: acrEndpoint
        authType: 'ManagedIdentity'
        credentials: {
          clientId: projectPrincipalId
          resourceId: acrResourceId
        }
        isSharedToAll: true
        metadata: {
          ResourceId: acrResourceId
        }
      }
    }
  }
}

output connectionName string = aiServices::project::acrConnection.name
