// RBAC role assignments
// Grants the Foundry project identity pull access to hosted-agent images.

targetScope = 'resourceGroup'

param acrId string
param projectPrincipalId string

// Extract ACR name from resource ID
var acrName = last(split(acrId, '/'))

// AcrPull role definition ID (built-in Azure role)
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

// Reference existing ACR resource
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

// Grant AI Services managed identity AcrPull access to ACR
resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acrId, projectPrincipalId, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: projectPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output acrPullRoleAssignmentId string = acrPullRoleAssignment.id
