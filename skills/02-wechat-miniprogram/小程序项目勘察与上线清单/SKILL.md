---
name: wechat-miniapp-engineering-skill
description: Chinese-first WeChat Mini Program engineering workflow and local analysis skill. Use when Codex needs to inspect a WeChat native/miniprogram cloud project, create beginner-friendly product-to-engineering plans, map pages/components/cloud functions/data collections, gather task-relevant context, generate launch or CloudBase release checklists, run a mini program security quick scan, or replace the old wechat-miniapp-engineering MCP workflow without requiring MCP client configuration.
---

# WeChat Miniapp Engineering Skill

Use this skill as a self-contained replacement for the old local MCP server. The bundled CLI hides the MCP transport and exposes the same 25 tools, 20 resources, and 3 prompt workflows from `assets/mcp-server`.

## Quick Start

For most tasks, run the local CLI instead of configuring an MCP client. Treat `assets/mcp-server/` as bundled engine source and legacy maintenance material, not normal-user setup instructions. From inside the skill directory, either use the npm binary name or call the script directly:

```bash
npx --no-install miniapp-engineering list-tools
npx --no-install miniapp-engineering call-tool miniapp_inspect_project '{"projectPath":"/absolute/path/to/miniapp","includeReadme":true}'
node scripts/miniapp_engineering_cli.mjs call-tool miniapp_project_map '{"projectPath":"/absolute/path/to/miniapp","format":"markdown","detail_level":"standard"}'
node scripts/miniapp_engineering_cli.mjs call-tool miniapp_security_quick_scan '{"projectPath":"/absolute/path/to/miniapp","maxFindings":80}'
node scripts/miniapp_engineering_cli.mjs call-tool miniapp_inspect_project @/absolute/path/to/args.json
node scripts/miniapp_engineering_cli.mjs read-resource miniapp://checklists/cloudbase-release
```

Run bundled verification passes before trusting a changed copy:

```bash
npm run validate
```

This single command runs `node --check scripts/miniapp_engineering_cli.mjs`, `npm run smoke:test`, and `node scripts/miniapp_engineering_cli.mjs quick_validate`.

## Workflow

1. For an existing project, start with `miniapp_inspect_project`, then `miniapp_project_map`, then `miniapp_relevant_context` for the user's current task.
2. For a new idea, use `miniapp_generate_blueprint`, `miniapp_showcase_roadmap`, or `miniapp_work_breakdown` before editing code.
3. Before changing cloud functions, routes, privacy behavior, storage, or review materials, run `miniapp_cloudbase_release_preflight` and `miniapp_security_quick_scan`.
4. For debugging or handoff, use `miniapp_dev_recovery_playbook`, `miniapp_understand_file_role`, `miniapp_understand_feature_impact`, `miniapp_dependency_diagram`, and `miniapp_graph_stats`.
5. Keep outputs Chinese-first and beginner-friendly unless the user asks otherwise.

## References

- Read `references/capability-index.md` when you need the full tool/resource/prompt inventory or exact argument schemas.
- Read `references/workflows.md` for task recipes that translate common user requests into CLI calls.
- Read `references/safety-and-release.md` before scanning real customer projects, CloudBase releases, any public sharing decision, or security checks.
- The original MCP source, fixture project, docs, and smoke tests are bundled under `assets/mcp-server/` for traceability.

## Safety Rules

- Treat real mini program projects as private by default. Do not copy customer material, AppID, cloud file IDs, phone numbers, orders, tokens, cookies, private config, or secrets into public outputs.
- Use absolute project paths for local scanning. Do not scan home, `.ssh`, `.codex`, `.claude`, keychain, or unrelated private folders.
- Security scan output must report file path, line number, rule, severity, and remediation direction; avoid echoing raw secret-like values.
- Use official CloudBase or WeChat tools for actual deployment. This skill gives planning, inspection, validation, and release checklists; it does not replace human confirmation for production actions.
