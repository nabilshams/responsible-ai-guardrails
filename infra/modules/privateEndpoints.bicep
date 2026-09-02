// Private endpoints for all Azure resources
// Each endpoint is linked to appropriate private DNS zones for automatic resolution

targetScope = 'resourceGroup'

param location string
param tags object
param peSubnetId string

// Resource IDs to create private endpoints for
param aiServicesId string
param aiLanguageId string
param docIntelligenceId string
param amplsId string
param documentStorageId string

// Private DNS zone IDs for linking
param cognitiveServicesDnsZoneId string
param openaiDnsZoneId string
param aiServicesDnsZoneId string
param monitorDnsZoneId string
param omsDnsZoneId string
param odsDnsZoneId string
param agentSvcDnsZoneId string
param blobDnsZoneId string

// Private endpoint for AI Services (Foundry hub)
resource aiServicesPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-aiservices'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: peSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'aiservices-connection'
        properties: {
          privateLinkServiceId: aiServicesId
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
}

resource aiServicesPrivateEndpointDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: aiServicesPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'cognitiveservices-config'
        properties: {
          privateDnsZoneId: cognitiveServicesDnsZoneId
        }
      }
      {
        name: 'openai-config'
        properties: {
          privateDnsZoneId: openaiDnsZoneId
        }
      }
      {
        name: 'aiservices-config'
        properties: {
          privateDnsZoneId: aiServicesDnsZoneId
        }
      }
    ]
  }
}

// Private endpoint for AI Language
resource aiLanguagePrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-ailanguage'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: peSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'ailanguage-connection'
        properties: {
          privateLinkServiceId: aiLanguageId
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
}

resource aiLanguagePrivateEndpointDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: aiLanguagePrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'cognitiveservices-config'
        properties: {
          privateDnsZoneId: cognitiveServicesDnsZoneId
        }
      }
    ]
  }
}

// Private endpoint for Azure Document Intelligence
resource docIntelligencePrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-docintel'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: peSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'docintel-connection'
        properties: {
          privateLinkServiceId: docIntelligenceId
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
}

resource docIntelligencePrivateEndpointDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: docIntelligencePrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'cognitiveservices-config'
        properties: {
          privateDnsZoneId: cognitiveServicesDnsZoneId
        }
      }
    ]
  }
}

// Private endpoint for Azure Monitor Private Link Scope
resource amplsPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-ampls'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: peSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'ampls-connection'
        properties: {
          privateLinkServiceId: amplsId
          groupIds: [
            'azuremonitor'
          ]
        }
      }
    ]
  }
}

resource amplsPrivateEndpointDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: amplsPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'monitor-config'
        properties: {
          privateDnsZoneId: monitorDnsZoneId
        }
      }
      {
        name: 'oms-config'
        properties: {
          privateDnsZoneId: omsDnsZoneId
        }
      }
      {
        name: 'ods-config'
        properties: {
          privateDnsZoneId: odsDnsZoneId
        }
      }
      {
        name: 'agentsvc-config'
        properties: {
          privateDnsZoneId: agentSvcDnsZoneId
        }
      }
    ]
  }
}

resource documentStoragePrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-document-storage'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: peSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'document-storage-connection'
        properties: {
          privateLinkServiceId: documentStorageId
          groupIds: [
            'blob'
          ]
        }
      }
    ]
  }
}

resource documentStoragePrivateEndpointDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: documentStoragePrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'blob-config'
        properties: {
          privateDnsZoneId: blobDnsZoneId
        }
      }
    ]
  }
}

output aiServicesPrivateEndpointId string = aiServicesPrivateEndpoint.id
output aiLanguagePrivateEndpointId string = aiLanguagePrivateEndpoint.id
output docIntelligencePrivateEndpointId string = docIntelligencePrivateEndpoint.id
output amplsPrivateEndpointId string = amplsPrivateEndpoint.id
output documentStoragePrivateEndpointId string = documentStoragePrivateEndpoint.id
