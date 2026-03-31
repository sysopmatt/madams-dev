---
layout: post
title: "Migrating your DABs CI/CD from Terraform to the Direct Engine"
subtitle: "How to switch engines across one repo or hundreds without breaking anything"
tags: ["databricks", "asset bundles", "terraform", "ci/cd", "devops", "direct engine"]
author: Matt Adams
---

Declarative Automation Bundles (formerly Databricks Asset Bundles, though everyone still says DABs) have been using Terraform under the hood since day one. That's changing. Starting with CLI v0.279.0 and hitting Public Preview on April 1, 2026, there's a new **Direct Deployment Engine** that replaces Terraform entirely. It implements resource CRUD operations directly on top of the Databricks Go SDK, so the CLI is fully self-contained.

If you're running DABs in CI/CD with service principals or managed identities, this matters to you. The good news is your auth setup doesn't change. The things that do change are worth understanding before they surprise you in a pipeline run.

> **You might not need to do anything.** Around mid-2026, the CLI will auto-migrate existing Terraform-backed bundles to the direct engine during deploy. If you keep your CLI version current on your runners, the migration will just happen. The Terraform engine is expected to be fully removed by end of 2026.
>
> That said, there are good reasons to migrate early rather than waiting:
> - Your CI runners are behind firewalls or proxies that make downloading Terraform painful or flaky
> - You're hitting known Terraform bugs (destroy-recreate loops, zero-value drops, stale computed fields) that the direct engine doesn't have
> - You want the new plan/apply separation for approval gates in your pipeline
> - You'd rather migrate on your own schedule than have it happen automatically during a routine deploy
>
> If any of those apply, the rest of this post walks through how to do it manually, for a single repo or hundreds at once.

## Why the switch

Four reasons, roughly in order of how often they caused people pain:

1. **No more downloading Terraform at deploy time.** If you've ever dealt with corporate firewalls or air-gapped environments blocking the Terraform binary download, you know this one. The CLI is now the only binary you need.
2. **Licensing.** HashiCorp moved Terraform to the BSL license. Databricks would rather not ship a grey-area dependency.
3. **Better error messages.** Errors now reference `databricks.yml` instead of auto-generated `.tf.json` files. If you've ever tried to debug a Terraform error that pointed at a generated file you weren't supposed to edit, you'll appreciate this.
4. **Simpler internals.** The old architecture was CLI -> Terraform -> Terraform Provider, three separate processes. The direct engine collapses that into one.

## How it behaves differently from Terraform

Before you migrate, it's worth knowing where the direct engine doesn't behave identically to Terraform.

### Config changes are never ignored

Terraform sometimes silently ignored certain config changes in `databricks.yml`. The direct engine doesn't. Every YAML change triggers an update. This means your first deploy after migration might produce more updates than you expect, even if you haven't changed anything in your config. That's normal, it's just the engine being more thorough.

### Updates are in-place, not destroy-then-recreate

Terraform has a concept called `ForceNew` where changing certain fields destroys the entire resource and recreates it, even when the API supports an in-place update. This has bitten people in real ways:

- Changing `display_name` on a `databricks_service_principal` destroys and recreates the SP, potentially invalidating tokens ([#2360](https://github.com/databricks/terraform-provider-databricks/issues/2360))
- Server-set `catalog` drift on pipelines with `ingestion_definition` causes full pipeline destruction, losing run history ([#4418](https://github.com/databricks/terraform-provider-databricks/issues/4418))
- Setting `enable_elastic_disk = false` on an instance pool triggers an infinite destroy-recreate loop because Go's `omitempty` drops the `false` value ([#5462](https://github.com/databricks/terraform-provider-databricks/issues/5462))

The direct engine sidesteps all of this. It uses API `update` calls via the Go SDK directly, so in-place updates are the default whenever the API supports them. No `ForceNew`, no `omitempty` zero-value bugs.

### Renames are treated as delete + create

If you rename a resource key in `databricks.yml`, both engines treat it as "delete the old one, create a new one." This can cause data loss if you're not careful. The `bundle deployment bind` and `unbind` commands (available in both engines) let you reassociate resources without deleting them:

```bash
# Tell the engine that the renamed resource is the same as the existing one
databricks bundle deployment bind my_job --resource-id <existing-job-id> -t prod
```

Note that bind/unbind has limited resource type support. It doesn't cover Unity Catalog resources like catalogs or external locations yet ([#4842](https://github.com/databricks/cli/issues/4842)).

### Deleting resources

Removing a resource from `databricks.yml` deletes it from the workspace on the next deploy. Same behavior as Terraform. `bundle destroy` also works with the direct engine.

### `lifecycle.prevent_destroy` is currently ignored

This is a known bug. If you rely on `prevent_destroy` to protect resources from accidental deletion, be aware that the direct engine doesn't enforce it yet. Track [GitHub issue #4872](https://github.com/databricks/cli/issues/4872) for the fix.

### State file format change

The Terraform engine stored state in `terraform.tfstate`. The direct engine uses `resources.json`. If you have any CI/CD steps that read or parse the Terraform state file directly, those will break.

## Migrating a single repo

The migration itself is three commands:

```bash
# 1. Do one final Terraform-backed deploy to make sure state is clean
databricks bundle deploy -t prod

# 2. Convert the state file
databricks bundle deployment migrate -t prod

# 3. Verify no drift
databricks bundle plan -t prod
```

Step 2 converts `terraform.tfstate` to `resources.json` and renames the old file to `terraform.tfstate.migrated`. Step 3 should show no pending changes.

If something goes wrong, rollback is easy:

```bash
rm .databricks/bundle/prod/resources.json
databricks bundle deploy -t prod
```

That puts you back on the Terraform engine using the backed-up state.

### CLI version requirements

You need CLI **v0.279.0 or later**. You can migrate right now, you don't need to wait for GA. One gotcha: the migrate command itself still needs Terraform available to read the old state file. After migration, Terraform is no longer needed on the runner.

## Migrating CI/CD at scale

This is where it gets practical. If you're managing a DABs template that's deployed across dozens or hundreds of repos, you probably can't push code changes to each one on demand. Maybe changes go through an annual review process, or repos are owned by different teams with different cadences.

The good news: **you don't need to modify any repos.** The entire migration can be driven from the CI/CD runner level.

### The idempotent pipeline pattern

Add these two things to your shared CI/CD pipeline template:

1. Set the environment variable on the runner:

```yaml
env:
  DATABRICKS_BUNDLE_ENGINE: direct
```

2. Add the migration command before your deploy step:

```yaml
steps:
  - name: Migrate to direct engine (idempotent)
    run: databricks bundle deployment migrate -t $TARGET || true

  - name: Deploy
    run: databricks bundle deploy -t $TARGET
```

The `migrate` command is effectively idempotent. If the bundle has already been migrated, it exits 0 (the old state file was already renamed). The `|| true` handles two edge cases: bundles that have never been deployed (no state to migrate), and bundles that were created after the switch (no Terraform state exists).

This pattern is safe to leave in your pipeline permanently. It handles:
- **Existing Terraform bundles:** Migrates on first run, no-ops after that
- **New bundles:** Nothing to migrate, the env var tells the engine to use direct from the start
- **Already-migrated bundles:** No-op

### What about service principals and managed identities?

No changes needed. The direct engine uses the same Databricks authentication as the Terraform engine. Your service principal tokens, managed identity configurations, and OAuth setups all carry over. The engine change is purely about how the CLI talks to the Databricks API, not how it authenticates.

### The plan/apply separation pattern

If your pipeline has an approval gate between planning and applying changes, the direct engine has a nice new capability:

```yaml
steps:
  - name: Plan
    run: databricks bundle plan -t prod -o json > plan.json

  - name: Review
    # Your approval gate here, human review, automated checks, etc.

  - name: Apply
    run: databricks bundle deploy -t prod --plan plan.json
```

This is something you couldn't easily do with the Terraform engine.

## Timeline and what you can ignore for now

| When | What happens |
|------|-------------|
| Dec 2025 | Direct engine available as experimental (CLI v0.279.0) |
| April 1, 2026 | Public Preview |
| Mid-2026 | Direct engine becomes the default for new bundles. Auto-migration ships, meaning the CLI will automatically migrate existing Terraform bundles during deploy. At this point, just keeping the CLI current on your runners handles everything. |
| End of 2026 | Terraform engine removed from the CLI |

If you're not in a rush, the mid-2026 auto-migration milestone is probably the lowest-effort path. Just keep your CLI version up to date on runners and it'll handle the migration for you. But if you want to get ahead of it (or you're hitting Terraform download issues in locked-down environments), the pipeline pattern above works today.

One important note: the standalone [Databricks Terraform Provider](https://registry.terraform.io/providers/databricks/databricks/latest/docs) is **not** being deprecated. This is only about the Terraform engine embedded within the DABs CLI. If you use Terraform directly (outside of DABs), nothing changes for you.

## References

- [Direct Deployment Engine Documentation](https://docs.databricks.com/aws/en/dev-tools/bundles/direct)
- [Direct Engine Design Doc (GitHub)](https://github.com/databricks/cli/blob/main/docs/direct.md)
- [DABs Release Notes](https://docs.databricks.com/aws/en/release-notes/dev-tools/bundles)
- [`lifecycle.prevent_destroy` bug - GitHub #4872](https://github.com/databricks/cli/issues/4872)
- [Databricks CLI Releases](https://github.com/databricks/cli/releases)
- [Databricks Terraform Provider](https://registry.terraform.io/providers/databricks/databricks/latest/docs) (not being deprecated)
