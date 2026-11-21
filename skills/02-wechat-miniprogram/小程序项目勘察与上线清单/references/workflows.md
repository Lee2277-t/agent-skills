# Workflows

## Existing Project Triage

1. Run `miniapp_inspect_project` with the project root.
2. Run `miniapp_project_map` with `detail_level:"standard"`.
3. If the user has a concrete feature, run `miniapp_relevant_context` with `query` or `featureName`.
4. Summarize findings in Chinese: current structure, likely business modules, files to inspect first, and low-risk next steps.

## New Mini Program Planning

1. Use `miniapp_generate_blueprint` for general mini programs.
2. Use `miniapp_showcase_roadmap` for client photo/video showcase, private gallery, appointment, or studio package scenarios.
3. Use `miniapp_work_breakdown` on the first feature that will be implemented.
4. Convert outputs into implementation steps only after the MVP boundary is clear.

## Feature Impact Analysis

1. Run `miniapp_understand_feature_impact` with the feature name.
2. Run `miniapp_relevant_context` for the same target if code changes are likely.
3. Use `miniapp_dependency_diagram` when route/controller/data relationships are unclear.
4. Before editing, list the expected pages, components, cloud functions, collections, permission rules, and tests.

## Release Or Deployment Preflight

1. Use `miniapp_cloudbase_release_preflight` for cloud function deploy, mini program upload/review, full release, or artifact sharing readiness.
2. Use `miniapp_launch_checklist` for public mini program launch and review material.
3. Use `miniapp_security_quick_scan` before touching customer privacy, cloud storage, logs, or database rules.
4. Preserve manual confirmation gates for real CloudBase environments, official review uploads, and any public sharing or package publication decision.

## Debugging And Recovery

1. Use `miniapp_dev_recovery_playbook` with the closest topic.
2. Use `miniapp_understand_file_role` for the file the user is stuck on.
3. Use `miniapp_graph_stats` and `miniapp_dependency_diagram` if the issue spans routes, controllers, services, and pages.
4. Prefer small, verifiable fixes. For WeChat pages, always confirm the `.js/.json/.wxml/.wxss` four-file set and `app.json` registration.

## Public Documentation

1. Keep public README language clear about the project being a Codex skill, not an actively updated MCP package.
2. Route normal users to `scripts/miniapp_engineering_cli.mjs`; avoid asking them to edit MCP client config.
3. Do not publish private local profile data, optimization JSONL, cache JSON, real project paths, customer material, AppID, or cloud file IDs.
