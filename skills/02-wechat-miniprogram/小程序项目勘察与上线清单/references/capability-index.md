# Capability Index

This skill bundles the old `wechat-miniapp-engineering-mcp@0.6.0` engine and exposes its capabilities through `scripts/miniapp_engineering_cli.mjs`.

## Tools

Use `node scripts/miniapp_engineering_cli.mjs call-tool <name> '<jsonArgs>'`.

### Normal user tools

| Tool | Purpose |
| --- | --- |
| `miniapp_inspect_project` | Scan a local WeChat native/cloud mini program and summarize pages, tabBar, cloud functions, business modules, and next steps. |
| `miniapp_generate_blueprint` | Generate a product-to-engineering blueprint covering positioning, pages, data, cloud functions, UI, and launch. |
| `miniapp_showcase_roadmap` | Produce a beginner-friendly roadmap for client photo/video showcase mini programs. |
| `miniapp_work_breakdown` | Break a feature into requirements, UI, frontend, backend, QA, and launch tasks. |
| `miniapp_dev_recovery_playbook` | Explain recovery workflows for session drift, missing page files, cloud route/deploy issues, DevTools EISDIR, release problems, and delegation. |
| `miniapp_cloudbase_release_preflight` | Generate preflight checks for cloud function deploy, mini program upload/review, full release, or artifact sharing readiness. |
| `miniapp_launch_checklist` | Generate a WeChat mini program launch checklist, including privacy and private album delivery. |
| `miniapp_docs_lookup` | Look up bundled official docs, GitHub projects, and engineering references by topic. |
| `miniapp_cloudbase_mcp_guide` | Explain how this local engineering skill should cooperate with official CloudBase tooling. |
| `miniapp_project_map` | Build a lightweight graph of pages, files, cloud functions, collections, components, and dependency edges. |
| `miniapp_understand_project_flow` | Explain the end-to-end mini program flow from requirements to launch. |
| `miniapp_understand_file_role` | Explain one file's role, upstream/downstream links, and beginner next steps. |
| `miniapp_understand_feature_impact` | Estimate what files, pages, cloud functions, data, permissions, tests, and release risks a feature may touch. |
| `miniapp_relevant_context` | Gather Core/Near/Extended/Background context for a task with a token budget. |
| `miniapp_dependency_diagram` | Generate Mermaid dependency diagrams for pages, routes, controllers, collections, and feature targets. |
| `miniapp_graph_stats` | Summarize graph node/edge types, route chains, important nodes, and risks. |
| `miniapp_index_status` | Compute safe text file hashes and compare with local cache; default is read-only. |
| `miniapp_security_quick_scan` | Run a static mini-program-specific security scan without printing raw secret values. |

### Maintainer and private-local tools

These are preserved for compatibility with the bundled MCP engine. Do not use them in normal public docs or beginner workflows unless the user explicitly asks for private local maintenance and confirms any local knowledge access.

| Tool | Purpose |
| --- | --- |
| `local_user_profile` | Summarize bundled/local work habits if present; avoid publishing private profile details. |
| `local_skill_routing` | Recommend Codex/Claude skills for mini program engineering subtasks. |
| `local_mcp_optimization_advice` | Produce improvement advice for the original MCP-style engine. |
| `yunyu_query_context` | Requires explicit confirmation before reading any external local knowledge route; default call returns a confirmation guard. |
| `local_mcp_append_optimization_log` | Append a local optimization log entry inside the bundled engine. Use only for private/local iteration. |
| `local_mcp_read_optimization_log` | Read recent local optimization log entries. |
| `local_mcp_optimization_log_status` | Report optimization log paths, counts, and recording rules. |

## Resources

Use `node scripts/miniapp_engineering_cli.mjs read-resource <uri>`.

- `miniapp://docs/index`
- `miniapp://project/current`
- `miniapp://checklists/launch`
- `miniapp://roadmap/showcase`
- `miniapp://playbooks/dev-recovery`
- `miniapp://checklists/cloudbase-release`
- `miniapp://cloudbase/mcp-guide`
- `miniapp://user/profile`
- `miniapp://user/skill-routing`
- `miniapp://audit/optimization-advice`
- `miniapp://audit/optimization-log`
- `miniapp://audit/optimization-log/latest`
- `miniapp://audit/optimization-log/status`
- `miniapp://understand/project-map`
- `miniapp://understand/project-flow`
- `miniapp://understand/relevant-context`
- `miniapp://understand/dependency-diagram`
- `miniapp://understand/graph-stats`
- `miniapp://audit/security-quick-scan`
- `miniapp://understand/index-status`

## Prompts

Use `node scripts/miniapp_engineering_cli.mjs get-prompt <name> '<jsonArgs>'`.

- `miniapp_product_manager`: clarify mini program requirements and version boundaries from an idea.
- `miniapp_engineering_reviewer`: review pages, tables, cloud functions, permissions, and launch checklist completeness.
- `miniapp_xiaoli_engineering_planner`: plan mini program engineering work in a Chinese-first, checklist-oriented style.

## Common Argument Patterns

```bash
node scripts/miniapp_engineering_cli.mjs call-tool miniapp_generate_blueprint '{"productName":"客户成片展示小程序","brandName":"示例摄影工作室","depth":"mvp","linkExistingProject":false}'
node scripts/miniapp_engineering_cli.mjs call-tool miniapp_work_breakdown '{"featureName":"私密相册","phase":"all"}'
node scripts/miniapp_engineering_cli.mjs call-tool miniapp_relevant_context '{"projectPath":"/absolute/path/to/project","query":"客户私密相册","budget":8000,"detail_level":"standard"}'
node scripts/miniapp_engineering_cli.mjs call-tool miniapp_cloudbase_release_preflight '{"action":"full-release","cloudFunctionName":"mcloud","envId":"demo-env","version":"1.2.0"}'
```

## Validation

Before trusting a changed copy of the skill, run:

```bash
npm run validate
```

This single script keeps the syntax check, smoke test, and quick validation together so a changed copy is not accepted after only one partial pass.
