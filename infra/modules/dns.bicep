// Private DNS zones for all private endpoint types
// Links each zone to the VNet for automatic resolution

targetScope = 'resourceGroup'

param vnetId string
param tags object

// Cognitive Services (Azure AI Language)
resource cognitiveServicesDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.cognitiveservices.azure.com'
  location: 'global'
  tags: tags
}

resource cognitiveServicesDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: cognitiveServicesDnsZone
  name: 'cognitiveservices-vnet-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetId
    }
  }
}

// OpenAI (Foundry may use this zone)
resource openaiDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.openai.azure.com'
  location: 'global'
  tags: tags
}

resource openaiDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: openaiDnsZone
  name: 'openai-vnet-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetId
    }
  }
}

// AI Services (Foundry AIServices)
resource aiServicesDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.services.ai.azure.com'
  location: 'global'
  tags: tags
}

resource aiServicesDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: aiServicesDnsZone
  name: 'aiservices-vnet-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetId
    }
  }
}

// Azure Monitor - main zone
resource monitorDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.monitor.azure.com'
  location: 'global'
  tags: tags
}

resource monitorDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: monitorDnsZone
  name: 'monitor-vnet-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetId
    }
  }
}

// Azure Monitor - OMS (Log Analytics ingestion)
resource omsDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.oms.opinsights.azure.com'
  location: 'global'
  tags: tags
}

resource omsDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: omsDnsZone
  name: 'oms-vnet-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetId
    }
  }
}

// Azure Monitor - ODS (Log Analytics data access)
resource odsDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.ods.opinsights.azure.com'
  location: 'global'
  tags: tags
}

resource odsDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: odsDnsZone
  name: 'ods-vnet-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetId
    }
  }
}

// Azure Automation (required for complete Azure Monitor Private Link Scope)
resource agentSvcDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.agentsvc.azure-automation.net'
  location: 'global'
  tags: tags
}

resource agentSvcDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: agentSvcDnsZone
  name: 'agentsvc-vnet-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetId
    }
  }
}

resource blobDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.blob.${environment().suffixes.storage}'
  location: 'global'
  tags: tags
}

resource blobDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: blobDnsZone
  name: 'blob-vnet-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetId
    }
  }
}

output cognitiveServicesDnsZoneId string = cognitiveServicesDnsZone.id
output openaiDnsZoneId string = openaiDnsZone.id
output aiServicesDnsZoneId string = aiServicesDnsZone.id
output monitorDnsZoneId string = monitorDnsZone.id
output omsDnsZoneId string = omsDnsZone.id
output odsDnsZoneId string = odsDnsZone.id
output agentSvcDnsZoneId string = agentSvcDnsZone.id
output blobDnsZoneId string = blobDnsZone.id
