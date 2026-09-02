// Network infrastructure: VNet, subnets, NSGs
// Agent subnet is delegated to Microsoft.App/environments for Foundry hosted agents

targetScope = 'resourceGroup'

param location string
param tags object
param vnetName string
param vnetAddressPrefix string
param agentSubnetName string
param agentSubnetPrefix string
param peSubnetName string
param peSubnetPrefix string
param nsgAgentName string
param nsgPeName string

// NSG for agent subnet (delegated to Microsoft.App/environments)
resource nsgAgent 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: nsgAgentName
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowAzureLoadBalancerInbound'
        properties: {
          description: 'Required for Azure Load Balancer health probes'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: 'AzureLoadBalancer'
          destinationAddressPrefix: '*'
          access: 'Allow'
          priority: 100
          direction: 'Inbound'
        }
      }
      {
        name: 'AllowVNetInbound'
        properties: {
          description: 'Allow traffic within VNet for agent communication'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          destinationAddressPrefix: 'VirtualNetwork'
          access: 'Allow'
          priority: 110
          direction: 'Inbound'
        }
      }
      {
        name: 'DenyAllInbound'
        properties: {
          description: 'Deny all other inbound traffic'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
          access: 'Deny'
          priority: 4096
          direction: 'Inbound'
        }
      }
      {
        name: 'AllowAzureServicesOutbound'
        properties: {
          description: 'Allow outbound to Azure services via service tags'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: 'VirtualNetwork'
          destinationAddressPrefix: 'AzureCloud'
          access: 'Allow'
          priority: 100
          direction: 'Outbound'
        }
      }
      {
        name: 'AllowVNetOutbound'
        properties: {
          description: 'Allow outbound within VNet for private endpoints'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          destinationAddressPrefix: 'VirtualNetwork'
          access: 'Allow'
          priority: 110
          direction: 'Outbound'
        }
      }
    ]
  }
}

// NSG for private endpoint subnet (minimal rules)
resource nsgPe 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: nsgPeName
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowVNetInbound'
        properties: {
          description: 'Allow traffic from VNet to private endpoints'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          destinationAddressPrefix: 'VirtualNetwork'
          access: 'Allow'
          priority: 100
          direction: 'Inbound'
        }
      }
      {
        name: 'DenyAllInbound'
        properties: {
          description: 'Deny all other inbound traffic'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
          access: 'Deny'
          priority: 4096
          direction: 'Inbound'
        }
      }
    ]
  }
}

// Virtual Network
resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix
      ]
    }
    subnets: [
      {
        name: agentSubnetName
        properties: {
          addressPrefix: agentSubnetPrefix
          networkSecurityGroup: {
            id: nsgAgent.id
          }
          delegations: [
            {
              name: 'Microsoft.App.environments'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
          serviceEndpoints: []
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: peSubnetName
        properties: {
          addressPrefix: peSubnetPrefix
          networkSecurityGroup: {
            id: nsgPe.id
          }
          delegations: []
          serviceEndpoints: []
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

output vnetId string = vnet.id
output vnetName string = vnet.name
output agentSubnetId string = '${vnet.id}/subnets/${agentSubnetName}'
output peSubnetId string = '${vnet.id}/subnets/${peSubnetName}'
