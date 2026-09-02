// RBAC role assignments
// Grants the Foundry project identity pull access to hosted-agent images.

targetScope = 'resourceGroup'

param acrId string
param projectPrincipalId string
param documentStorageId string
param aiLanguagePrincipalId string

// Extract ACR name from resource ID
var acrName = last(split(acrId, '/'))

// AcrPull role definition ID (built-in Azure role)
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

// Reference existing ACR resource
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

resource documentStorage 'Microsoft.Storage/storageAccounts@2025-06-01' existing = {
  name: last(split(documentStorageId, '/'))
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

resource languageStorageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(documentStorageId, aiLanguagePrincipalId, storageBlobDataContributorRoleId)
  scope: documentStorage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalId: aiLanguagePrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource projectStorageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(documentStorageId, projectPrincipalId, storageBlobDataContributorRoleId)
  scope: documentStorage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalId: projectPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output acrPullRoleAssignmentId string = acrPullRoleAssignment.id
output languageStorageRoleAssignmentId string = languageStorageRoleAssignment.id
output projectStorageRoleAssignmentId string = projectStorageRoleAssignment.id
