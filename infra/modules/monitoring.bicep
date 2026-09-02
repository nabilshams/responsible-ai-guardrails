// Monitoring infrastructure: Log Analytics, Application Insights, Azure Monitor Private Link Scope
// Ingestion remains private; authenticated queries are available to portal experiences.

targetScope = 'resourceGroup'

param location string
param tags object
param logAnalyticsName string
param appInsightsName string
param amplsName string

// Log Analytics workspace
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    publicNetworkAccessForIngestion: 'Disabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// Application Insights
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    publicNetworkAccessForIngestion: 'Disabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// Azure Monitor Private Link Scope
resource ampls 'Microsoft.Insights/privateLinkScopes@2021-07-01-preview' = {
  name: amplsName
  location: 'global'
  tags: tags
  properties: {
    accessModeSettings: {
      ingestionAccessMode: 'PrivateOnly'
      queryAccessMode: 'PrivateOnly'
    }
  }
}

// Link Log Analytics to AMPLS
resource amplsLogAnalyticsLink 'Microsoft.Insights/privateLinkScopes/scopedResources@2021-07-01-preview' = {
  parent: ampls
  name: 'log-analytics-scoped-resource'
  properties: {
    linkedResourceId: logAnalytics.id
  }
}

// Link Application Insights to AMPLS
resource amplsAppInsightsLink 'Microsoft.Insights/privateLinkScopes/scopedResources@2021-07-01-preview' = {
  parent: ampls
  name: 'app-insights-scoped-resource'
  properties: {
    linkedResourceId: appInsights.id
  }
}

output logAnalyticsId string = logAnalytics.id
output logAnalyticsName string = logAnalytics.name
output appInsightsId string = appInsights.id
output appInsightsName string = appInsights.name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output amplsId string = ampls.id
