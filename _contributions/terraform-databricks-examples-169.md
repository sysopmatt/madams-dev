---
title: "Corrections for GCP SA Provisioning Example (Issue #168)"
project: "databricks/terraform-databricks-examples"
project_url: "https://github.com/databricks/terraform-databricks-examples"
contribution_url: "https://github.com/databricks/terraform-databricks-examples/pull/169"
contribution_type: "Pull Request"
status: "Merged"
date: "2024-12-28"
tags:
  - terraform
  - databricks
  - gcp
  - documentation
description: |
  Fixed several issues in the `gcp-sa-provisioning` Terraform example:
  - Corrected misspelled module directory name (`gcp-sa-provisionning` -> `gcp-sa-provisioning`).
  - Renamed example module reference to avoid conflict with `gcp-basic`.
  - Removed invalid `custom_role_url` output definition from the example.
  - Corrected misspelled `gcloud` command and other typos in the README.
--- 