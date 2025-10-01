---
layout: post
title: "Creating Reusable Databricks Asset Bundle (DAB) Templates"
subtitle: "Standardize project setup with interactive prompts following official conventions"
tags: ["databricks", "databricks asset bundles", "dabs", "templates", "automation", "standardization", "cicd", "devops"]
author: Matt Adams
---


As teams adopt Databricks Asset Bundles (DABs) for managing projects, ensuring consistency and accelerating setup becomes crucial. Instead of copying and pasting configurations, you can create **DAB Templates**. These templates allow you to define a standard project structure and configuration, while prompting the user for specific details (like project names, workspace URLs, or the project's purpose) during initialization using a structured schema.

This guide demonstrates how to build a DAB template following the official Databricks conventions, using a JSON schema for prompts and a nested template structure.

**Download Example Template Files:**

You can find the example template files used in this post (including the schema, bundle config, job resource, and placeholder notebook) in the following directory on GitHub:

*   [Example DAB Template Assets](https://github.com/sysopmatt/madams-dev/tree/main/assets/blog_post_assets/creating-databricks-asset-bundle-templates/)

## Understanding the Official DAB Template Structure

The official convention for Databricks Asset Bundle templates involves a specific structure:

1.  **`databricks_template_schema.json` (Root Level):** This JSON file defines the input variables (prompts) presented to the user during `databricks bundle init`. It uses JSON Schema properties to define each prompt's name, description, type, default value, etc.
2.  **`template/` Directory (Root Level):** This directory contains the actual template files that will be copied and processed to create the new bundle project.
3.  **`template/{% raw %}{{.project_name}}{% endraw %}/` Subdirectory:** Inside the `template` directory, a subdirectory named using the Go template variable `{% raw %}{{.project_name}}{% endraw %}` (or another variable defined in the schema) is required. This subdirectory contains the core template files:
    *   `databricks.yml.tmpl`: The template for the main bundle configuration file.
    *   `resources/`: A subdirectory typically containing resource definition templates (e.g., `{% raw %}{{.project_name}}{% endraw %}_job.yml.tmpl`).
    *   `src/`: A subdirectory typically containing source code like notebooks or Python files.

**Key Differences from Older Methods:**

*   Prompts are defined in `databricks_template_schema.json`, not within a `template:` block in `databricks.yml.tmpl`.
*   Input variables defined in the JSON schema are accessed within `.tmpl` files using the syntax `{% raw %}{{.variable_name}}{% endraw %}` (e.g., `{% raw %}{{.project_name}}{% endraw %}`), **without** the `input_` prefix.
*   The template files reside within the nested `template/{% raw %}{{.project_name}}{% endraw %}/` structure.

**The `.tmpl` Extension Convention:**

As mentioned before, using the `.tmpl` extension for files containing Go template syntax (`{% raw %}{{.variable_name}}{% endraw %}`) is a helpful convention for clarity. The `bundle init` command processes these files and saves the output without the `.tmpl` extension in the generated project.

## Example Official DAB Template

**Template Project Structure:**

```
my-official-dab-template/
├── databricks_template_schema.json  # Defines prompts
└── template/
    └── {% raw %}{{.project_name}}{% endraw %}/             # Core template files reside here
        ├── databricks.yml.tmpl
        ├── resources/
        │   └── {% raw %}{{.project_name}}{% endraw %}_job.yml.tmpl # Resource template using project name
        └── src/
            └── placeholder_notebook.py
```

### Template Schema (`databricks_template_schema.json`)

```json
{
  "properties": {
    "project_name": {
      "type": "string",
      "description": "Enter a short, descriptive name for this project (used in names, paths)",
      "default": "my_databricks_project"
    },
    "bundle_purpose": {
      "type": "string",
      "description": "Select the primary purpose (e.g., ETL, Analytics, ML Training, ML Inference)",
      "default": "Analytics"
    },
    "databricks_host_prod": {
      "type": "string",
      "description": "Enter the Databricks workspace URL for the PROD environment"
    },
    "workspace_root_path": {
      "type": "string",
      "description": "Enter the root path in the Databricks workspace for deployment (e.g., /Shared/Bundles)",
      "default": "/Shared/Bundles"
    },
    "team_permission_group": {
      "type": "string",
      "description": "Enter the Databricks group name for team MANAGE permissions (optional, leave blank if none)",
      "default": "data_engineering"
    }
  },
  "required": [
    "project_name",
    "bundle_purpose",
    "databricks_host_prod"
  ]
}
```

**Explanation:**

*   Uses standard JSON Schema format.
*   Defines properties for `project_name`, `bundle_purpose`, etc., with types, descriptions, and defaults.
*   The `required` array lists variables that *must* be provided by the user.

### Bundle Configuration Template (`template/{% raw %}{{.project_name}}{% endraw %}/databricks.yml.tmpl`)

This file is now simpler, as prompts are externalized. Note the variable access `{% raw %}{{.variable_name}}{% endraw %}`.

```yaml
# Located inside template/{% raw %}{{.project_name}}{% endraw %}/databricks.yml.tmpl
bundle:
  # Bundle name is derived from the directory name created by init
  name: {% raw %}{{.project_name}}{% endraw %}

# Define deployment targets using the input variables
targets:
  dev:
    mode: development
    default: true

  prod:
    mode: production
    host: "{% raw %}{{.databricks_host_prod}}{% endraw %}" 
    root_path: "{% raw %}{{.workspace_root_path}}{% endraw %}/{% raw %}{{.project_name}}{% endraw %}/prod"

# Include resource definition files
# Path is relative to this databricks.yml.tmpl file
include:
  - resources/*.yml

# Define permissions for the bundle artifacts using input variables
permissions:
  - level: CAN_MANAGE
    {{- if .team_permission_group }}
    group_name: "{% raw %}{{.team_permission_group}}{% endraw %}"
    {{- end }}
  - level: CAN_VIEW
    group_name: users
```

**Explanation:**

*   Variables are accessed directly, e.g., `{% raw %}{{.project_name}}{% endraw %}`, `{% raw %}{{.databricks_host_prod}}{% endraw %}`.
*   The `include` path is relative to this file within the `template/{% raw %}{{.project_name}}{% endraw %}` structure.


### Example Job Resource Template (`template/{% raw %}{{.project_name}}{% endraw %}/resources/{% raw %}{{.project_name}}{% endraw %}_job.yml.tmpl`)

This job definition template uses the variables and follows the naming convention.

```yaml
# Located inside template/{% raw %}{{.project_name}}{% endraw %}/resources/{% raw %}{{.project_name}}{% endraw %}_job.yml.tmpl
resources:
  jobs:
    # Resource key can also use variables if needed, though static is often simpler
    {% raw %}{{.project_name}}{% endraw %}_job:
      name: "[{% raw %}{{.project_name}}{% endraw %}] Basic Job (${bundle.target})"
      tags:
        project: "{% raw %}{{.project_name}}{% endraw %}"
        purpose: "{% raw %}{{.bundle_purpose}}{% endraw %}"
        source: "DAB Template"
      tasks:
        - task_key: run_notebook
          notebook_task:
            # Path relative to the root of the *generated* bundle (databricks.yml location)
            notebook_path: ../src/placeholder_notebook.py

      permissions:
       {{- if .team_permission_group }}
        - level: CAN_MANAGE
          group_name: "{% raw %}{{.team_permission_group}}{% endraw %}"
       {{- end }}
        - level: CAN_VIEW
          group_name: users
```

**Explanation:**

*   The filename itself (`{% raw %}{{.project_name}}{% endraw %}_job.yml.tmpl`) uses template syntax.
*   The resource key `{% raw %}{{.project_name}}{% endraw %}_job:` also uses the variable.
*   Variable access is `{% raw %}{{.variable_name}}{% endraw %}`.
*   The `notebook_path` is relative to the location of the generated `databricks.yml` file.

### Placeholder Notebook (`template/{% raw %}{{.project_name}}{% endraw %}/src/placeholder_notebook.py`)

This file remains unchanged as it contains no template variables.

```python
# Located inside template/{% raw %}{{.project_name}}{% endraw %}/src/placeholder_notebook.py
# Databricks notebook source

print("This is a placeholder notebook generated from the DAB template.")

# TODO: Replace this with actual project logic.

# Example: Accessing bundle variables (if passed via job parameters)
# dbutils.widgets.text("project_name", "default_project")
# project_name = dbutils.widgets.get("project_name")
# print(f"Running notebook for project: {project_name}")

# Example: Getting the purpose tag (if passed as a parameter)
# dbutils.widgets.text("purpose", "default_purpose")
# purpose = dbutils.widgets.get("purpose")
# print(f"Notebook purpose: {purpose}")
```

## Using the Template

To create a new project based on this official template structure:

1.  **Navigate:** Open your terminal where you want the new project.
2.  **Initialize:** Run `databricks bundle init <template_source>`.
3.  **Answer Prompts:** Provide values based on the descriptions defined in `databricks_template_schema.json`.
4.  **Project Generated:** A new directory named after the `project_name` you entered is created. Inside, the files from the template's `template/{% raw %}{{.project_name}}{% endraw %}/` directory are copied, processed (substituting `{% raw %}{{.variable_name}}{% endraw %}` values), and renamed (e.g., `.tmpl` removed, filenames with variables resolved).

# Conclusion

Following the official Databricks Asset Bundle template structure using `databricks_template_schema.json` provides a robust and standardized way to create reusable project starters. While slightly more complex initially, it clearly separates prompt definitions from configuration logic, leading to cleaner and more maintainable templates, especially as they grow in complexity.

# References

Here are links to the official documentation for the key concepts discussed in this post:

*   **Databricks Asset Bundles Documentation**
    *   [Databricks Asset Bundles overview](https://docs.databricks.com/en/dev-tools/bundles/index.html) - Main documentation for DABs.
    *   [Develop a Databricks Asset Bundle template](https://docs.databricks.com/en/dev-tools/bundles/templates.html) - Official guide on creating templates, including the `databricks_template_schema.json` structure.
    *   [Databricks Asset Bundles configuration](https://docs.databricks.com/en/dev-tools/bundles/settings.html) - Details on `databricks.yml` settings.
*   **Go Templates**
    *   [Go `text/template` Package Documentation](https://pkg.go.dev/text/template) - Official documentation for the Go template language used by Databricks Asset Bundles for variable substitution (`{% raw %}{{.variable_name}}{% endraw %}`).