---
layout: post
title: "Databricks LakeFlow Connect Using Databricks Asset Bundles (DAB) for SQL Server Replication"
subtitle: Implementing CI/CD build pipeline with DABs for Lakeflow Connect replication
thumbnail-img: /assets/img/lakeflow-database-connector-components.png
share-img: /assets/img/lakeflow-database-connector-components.png
tags: ["databricks", "delta live tables", "lakeflow", "replication"]
author: Matt Adams
---


Databricks LakeFlow Connect is currently in Gated Public Preview.  As this is the case, there isn't a ton of documentation around setting up CI/CD processes using Databricks Asset Bundles (DAB).  Fortunately the setup is pretty straight forward, and I found it to already be supported by DABs.   Ok let's get into it!

## Background on LakeFlow Connect 

[Databricks LakeFlow Connect](https://learn.microsoft.com/en-us/azure/databricks/ingestion/lakeflow-connect/) uses Delta Live Tables (DLT) pipelines as the back-end for the replication.  This makes tapping in to the DAB deployments pretty simple.

LakeFlow Connect requires two DLT pipelines.  One is for the gateway, which runs regular job compute and is what connects from within your tenant to your connected SQL Server.  

![Source: Databricks](/assets/img/lakeflow-database-connector-components.png "Source: Databricks")
_Source: [Databricks](https://learn.microsoft.com/en-us/azure/databricks/ingestion/lakeflow-connect/)_

# Create ADO build pipeline

First thing's first, I wanted an ADO build pipeline that just deploys to production.  For this initial use-case, I didn't need to build separately to development and QA environments, I really just needed a build straight to production.

```yaml
############################
# azurepipelines.yml
#

stages:

- stage: Initialize
  jobs:
  - job: Initialize
    pool: VMSS Build Agents # WE USE VMSS POOLS, YOU MAY HAVE TO TWEAK THIS DEPENDING ON THE TYPE OF COMPUTE YOUR BUILD PIPELINES CAN USE, WHICH VARIES DEPENDING ON YOUR SECURITY

    steps:
    - script: env | sort
      displayName: 'Environment / Context'

    - checkout: self
      displayName: 'Checkout & Build.Reason: $(Build.Reason) & Build.SourceBranchName: $(Build.SourceBranchName)'
      persistCredentials: true
      clean: true

  variables:
  - group: "Databricks PROD"


- stage: DeployToProd
  dependsOn:
    - Initialize 
  condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))

  jobs:
  - job: DeployProd
    pool: VMSS Build Agents

    steps:
    - script: env | sort
      displayName: 'Environment / Context'

    - checkout: self
      displayName: 'Checkout & Build.Reason: $(Build.Reason) & Build.SourceBranchName: $(Build.SourceBranchName)'
      persistCredentials: true
      clean: true

    # Validate bundle
    - script: |
        databricks bundle validate -t prod
      displayName: 'Validate bundle'
      env:
        ARM_TENANT_ID: $(TenantID)
        ARM_CLIENT_ID: $(REPLICATION-SERVICE-PRINCIPAL-client-id)
        ARM_CLIENT_SECRET: $(REPLICATION-SERVICE-PRINCIPAL-secret)

    # Deploy bundle 
    - script: |
        databricks bundle deploy -t prod
      displayName: 'Deploy bundle'
      env:
        ARM_TENANT_ID: $(TenantID)
        ARM_CLIENT_ID: $(REPLICATION-SERVICE-PRINCIPAL-client-id)
        ARM_CLIENT_SECRET: $(REPLICATION-SERVICE-PRINCIPAL-secret)

  variables:
  - group: "Databricks PROD"
```

# Create DAB

Like I mentioned before, the DAB needs to have a gateway pipeline and an ingestion pipeline, and if you would like to run the ingestion pipeline on a schedule, you'll need a regular scheduled job as well.

A couple big tips here:
1. The service principal that I used above, `REPLICATION-SERVICE-PRINCIPAL`, will be the service principal that runs the DLT pipelines.  That user will need permissions in the following areas:
    1. Within the Databricks workspace that you are deploying to
    1. To the connection (`connexample` in the example below) which is stored in Unity Catalog's External Connections
    1. To the Unity Catalog catalog and schema which you are replicating into.

## Setup connection to SQL Server

First you will need to setup a connection to SQL Server in Unity Catalog -> External Connections.

On the first tab, it's imporant to select SQL Server as the connection type, and username and password as the auth type.  Other than that, it should be pretty straight forward when you fill these out.

![Source: Databricks](/assets/img/create-connection.png "Source: Databricks")


## Databricks Asset Bundle - Setup

I have created a template internally that we use for quickly deploying new DABs, but for this example I'll go ahead and use one of the default templates built into the Databricks CLI.



## Create gateway pipeline

The Gateway pipeline is the easier of the two pipelines.  Most of this is something you can copy/paste, with very minimal changes on your end.

Here is a list of what the objects below represent:

- `replicated`      =       catalog which we are replicating the data to
- `lf_example`      =       schema which we are replicating to in the above catalog
- `connexample`     =       the connection you setup in UC's External Connections
- `my_team`         =       a Databricks group which contains the people on my team that will co-manage this job

```yaml
############################
# example_gateway.yml
#

resources:
  pipelines:
    pipeline_example_gateway:
      name: example_gateway
      channel: PREVIEW # THIS IS SUPER IMPORTANT.  YOU MUST RUN THIS PIPELINE IN THE `PREVIEW` CHANNEL IN ORDER TO USE LAKEFLOW CONNECT PIPELINES.
      clusters:
        - label: updates
          spark_conf:
            gateway.logging.level: INFO # 'DEBUG' IS AN ALTERNATE OPTION IF YOU NEED TO DEBUG THE PIPELINE.  DO NOT RUN A PRODUCTION PIPELINE WITH DEBUG LOGGING, HOWEVER, AS IT WILL GENERATE AN EXCESSIVE AMOUNT OF LOGS.
      gateway_definition:
        connection_name: connexample
        connection_id: df1e950c-9aef-417d-949e-87812d6b11e5 # YOU WILL NEED TO COPY THIS UUID FROM YOUR CONNECTION. A LOOKUP FOR CONNECTIONS IS NOT YET SUPPORTED IN DATABRICKS ASSET BUNDLES.
        gateway_storage_catalog: replicated
        gateway_storage_schema: lf_example
        gateway_storage_name: lf_example
        source_type: SQLSERVER
      target: lf_example
      continuous: true
      catalog: replicated

      permissions:
        - group_name: my_team
          level: CAN_MANAGE
```

## Create ingestion pipeline

Here is a list of what the objects below represent:

- `replicated`      =       catalog which we are replicating the data to
- `lf_example`      =       schema which we are replicating to in the above catalog
- `connexample`     =       the connection you setup in UC's External Connections
- `my_team`         =       a Databricks group which contains the people on my team that will co-manage this job
- `source_database` =       the *case sensitive* name of the database on the source SQL server

The most important part of the ingestion pipeline is the `objects` section.  This is where you will create a `table` object for each table you wish to replicate.  As of writing this, they are recommending no more than 100 tables per ingestion and gateway pipeline.  You will need to split large databases out into multiple pipelines.

```yaml
############################
# example_ingestion.yml
#

variables:
  example_gateway:
    lookup:
      pipeline: "example_gateway"

resources:
  pipelines:
    pipeline_aux_data_ingestion:
      name: example_ingestion
      channel: PREVIEW
      ingestion_definition:
        ingestion_gateway_id: ${var.example_gateway}
        objects:
          - table:
              source_catalog: source_database # ALTHOUGH IT ASKS FOR THE SOURCE DATABASE TO BE INPUTTED ON EACH TABLE, YOU CANNOT REPLICATE FROM MULTIPLE DATABASES ON THE SAME INGESTION PIPELINE.
              source_schema: dbo              # MULTIPLE SCHEMAS ARE SUPPORTED, HOWEVER!
              source_table: example_table_1
              destination_catalog: replicated
              destination_schema: lf_example
          - table:
              source_catalog: source_database
              source_schema: archive
              source_table: example_table_1
              destination_catalog: replicated
              destination_schema: lf_example

        source_type: SQLSERVER
      target: lf_example
      photon: true
      catalog: replicated
      serverless: true

      permissions:
        - group_name: my_team
          level: CAN_MANAGE
```

## Create job to run ingestion on a schedule

On this job, the only thing I do that's a little bit trickier here is that I use a lookup variable.  The purpose of this lookup variable is to pull the UUID of the ingestion pipeline, so that we don't have to hard code it.  It will perform a lookup based on the name we give it.  This way if you have to redeploy the whole pipeline, a changing UUID won't mess you up too much.

```yaml
############################
# run_ingestion_pipelines.yml
#

variables:
  example_ingestion:
    lookup:
      pipeline: "example_ingestion"

resources:
  jobs:
    run_ingestion_pipelines: 
      name: run_ingestion_pipelines
      
      tasks:
        - task_key: example_ingestion
          pipeline_task:
            pipeline_id: ${var.example_ingestion}
      
      schedule:
        quartz_cron_expression: 0 14/30 * * * ?
        timezone_id: America/Los_Angeles
        pause_status: ${var.paused}   

      permissions:
        - group_name: my_team
          level: CAN_MANAGE
```

# Conclusion

Setting up and maintaining the DAB for LakeFlow Connect SQL Replication is actually quite a bit easier than using the REST API or Python SDK via notebooks.  Modifying which tables you are replicating is as easy as modifying the YAML and pushing to Azure DevOps and letting your build pipeline take over, with the added benefit of built in approvals and version history, so you know who is making changes, when the changes are made, and who approved them, for a proper CI/CD flow.