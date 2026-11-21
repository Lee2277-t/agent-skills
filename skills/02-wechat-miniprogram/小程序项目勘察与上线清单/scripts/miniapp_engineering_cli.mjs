#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import readline from "node:readline";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const skillRoot = path.resolve(__dirname, "..");
const engineRoot = path.join(skillRoot, "assets", "mcp-server");
const serverPath = path.join(engineRoot, "src", "server.js");
const fixtureProjectPath = process.env.SMOKE_PROJECT_PATH || path.join(engineRoot, "data", "fixtures", "demo-miniapp");
const requestTimeoutMs = parsePositiveIntegerEnv("MINIAPP_ENGINEERING_TIMEOUT_MS", 20000);

function parsePositiveIntegerEnv(name, fallback) {
  const raw = process.env[name];
  if (!raw) return fallback;
  const value = Number(raw);
  if (!Number.isInteger(value) || value <= 0) throw new Error(`${name} must be a positive integer number of milliseconds.`);
  return value;
}

function usage(exitCode = 0) {
  const text = [
    "Usage:",
    "  node scripts/miniapp_engineering_cli.mjs list-tools",
    "  node scripts/miniapp_engineering_cli.mjs call-tool <toolName> '<jsonObjectArgs|@/absolute/path/to/args.json>'",
    "  node scripts/miniapp_engineering_cli.mjs list-resources",
    "  node scripts/miniapp_engineering_cli.mjs read-resource <uri>",
    "  node scripts/miniapp_engineering_cli.mjs list-prompts",
    "  node scripts/miniapp_engineering_cli.mjs get-prompt <promptName> '<jsonObjectArgs|@/absolute/path/to/args.json>'",
    "  node scripts/miniapp_engineering_cli.mjs smoke",
    "  node scripts/miniapp_engineering_cli.mjs quick_validate",
    "  node scripts/miniapp_engineering_cli.mjs index-status ['<jsonObjectArgs|@/absolute/path/to/args.json>']"
  ].join("\n");
  console.log(text);
  process.exit(exitCode);
}

function parseJsonObjectArg(raw, fallback = {}) {
  if (!raw) return fallback;
  const value = raw.startsWith("@") ? readJsonArgFile(raw.slice(1)) : raw;
  let parsed;
  try {
    parsed = JSON.parse(value);
  } catch (err) {
    throw new Error(`Invalid JSON argument: ${err instanceof Error ? err.message : String(err)}`);
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("Invalid JSON argument: expected a JSON object, for example '{\"projectPath\":\"/absolute/path/to/miniapp\"}'.");
  }
  return parsed;
}

function readJsonArgFile(filePath) {
  if (!filePath) throw new Error("Invalid JSON argument file: expected @/absolute/path/to/args.json.");
  if (!path.isAbsolute(filePath)) throw new Error("Invalid JSON argument file: @file must use an absolute path.");
  let stat;
  try {
    stat = fs.statSync(filePath);
  } catch (err) {
    throw new Error(`Invalid JSON argument file: cannot read ${filePath}. ${err instanceof Error ? err.message : String(err)}`);
  }
  if (!stat.isFile()) throw new Error(`Invalid JSON argument file: ${filePath} is not a file.`);
  if (stat.size > 1024 * 1024) throw new Error(`Invalid JSON argument file: ${filePath} is larger than 1 MiB.`);
  return fs.readFileSync(filePath, "utf8");
}

function extractText(payload) {
  const result = payload?.result;
  if (Array.isArray(result?.content) && result.content[0]?.text) return result.content[0].text;
  if (Array.isArray(result?.contents) && result.contents[0]?.text) return result.contents[0].text;
  return JSON.stringify(result ?? payload, null, 2);
}

function validateCliToolArgs(toolName, args) {
  if (!Object.hasOwn(args, "projectPath")) return args;
  if (typeof args.projectPath !== "string" || !path.isAbsolute(args.projectPath)) {
    throw new Error(`Invalid arguments for ${toolName}: projectPath must be an absolute path to the target mini program project.`);
  }
  return args;
}

async function withServer(fn) {
  const child = spawn(process.execPath, [serverPath], {
    cwd: engineRoot,
    stdio: ["pipe", "pipe", "pipe"]
  });
  const responses = new Map();
  const waiters = new Map();
  const stderr = [];
  let nextId = 1;

  const rl = readline.createInterface({ input: child.stdout, crlfDelay: Infinity });
  rl.on("line", (line) => {
    if (!line.trim()) return;
    let message;
    try {
      message = JSON.parse(line);
    } catch (err) {
      stderr.push(`Invalid JSON from engine: ${line}`);
      return;
    }
    responses.set(message.id, message);
    const waiter = waiters.get(message.id);
    if (waiter) {
      waiters.delete(message.id);
      waiter.resolve(message);
    }
  });
  child.stderr.on("data", (chunk) => stderr.push(String(chunk)));

  function rejectPendingWaiters(reason) {
    for (const [id, waiter] of waiters.entries()) {
      waiters.delete(id);
      waiter.reject(reason);
    }
  }

  child.on("error", (err) => {
    rejectPendingWaiters(new Error(`Engine process error: ${err.message}. Engine stderr:\n${stderr.join("").trim()}`));
  });
  child.on("exit", (code, signal) => {
    if (waiters.size > 0) {
      rejectPendingWaiters(new Error(`Engine exited before responding (code ${code ?? "null"}, signal ${signal ?? "null"}). Engine stderr:\n${stderr.join("").trim()}`));
    }
  });

  function request(method, params = {}) {
    const id = nextId++;
    const message = { jsonrpc: "2.0", id, method, params };
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        waiters.delete(id);
        reject(new Error(`Timed out waiting for ${method}. Engine stderr:\n${stderr.join("").trim()}`));
      }, requestTimeoutMs);
      waiters.set(id, {
        resolve: (value) => {
          clearTimeout(timeout);
          resolve(value);
        },
        reject: (reason) => {
          clearTimeout(timeout);
          reject(reason);
        }
      });
      if (responses.has(id)) {
        const response = responses.get(id);
        responses.delete(id);
        waiters.delete(id);
        clearTimeout(timeout);
        resolve(response);
        return;
      }
      child.stdin.write(`${JSON.stringify(message)}\n`, (err) => {
        if (err) {
          waiters.delete(id);
          clearTimeout(timeout);
          reject(new Error(`Failed to write ${method} request to engine: ${err.message}`));
        }
      });
    });
  }

  try {
    const init = await request("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "wechat-miniapp-engineering-skill-cli", version: "0.1.0" }
    });
    if (init.error) throw new Error(init.error.message);
    child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" })}\n`);
    return await fn({ request, responses });
  } finally {
    child.stdin.end();
    setTimeout(() => {
      if (!child.killed && child.exitCode === null) child.kill("SIGTERM");
    }, 500);
  }
}

function assertOk(name, condition, details = "") {
  return { name, ok: Boolean(condition), details };
}

async function runSmoke() {
  const checks = await withServer(async ({ request }) => {
    const tools = await request("tools/list", {});
    const resources = await request("resources/list", {});
    const prompts = await request("prompts/list", {});
    const toolNames = tools.result?.tools?.map((tool) => tool.name) || [];
    const resourceUris = resources.result?.resources?.map((resource) => resource.uri) || [];
    const promptNames = prompts.result?.prompts?.map((prompt) => prompt.name) || [];
    const inspect = await request("tools/call", {
      name: "miniapp_inspect_project",
      arguments: { projectPath: fixtureProjectPath, includeReadme: false }
    });
    const logStatus = await request("tools/call", {
      name: "local_mcp_optimization_log_status",
      arguments: {}
    });
    const projectFlow = await request("tools/call", {
      name: "miniapp_understand_project_flow",
      arguments: { projectPath: fixtureProjectPath, goal: "客户成片展示小程序", limit: 200 }
    });
    const relevantContext = await request("tools/call", {
      name: "miniapp_relevant_context",
      arguments: { projectPath: fixtureProjectPath, query: "客户私密相册", limit: 220, budget: 3000, detail_level: "summary" }
    });
    const graphStats = await request("tools/call", {
      name: "miniapp_graph_stats",
      arguments: { projectPath: fixtureProjectPath, limit: 220 }
    });
    const dependencyDiagram = await request("tools/call", {
      name: "miniapp_dependency_diagram",
      arguments: { projectPath: fixtureProjectPath, target: "客户私密相册", limit: 220 }
    });
    const map = await request("tools/call", {
      name: "miniapp_project_map",
      arguments: { projectPath: fixtureProjectPath, limit: 220, format: "json", detail_level: "full" }
    });
    const indexStatus = await request("tools/call", {
      name: "miniapp_index_status",
      arguments: { projectPath: fixtureProjectPath, limit: 220 }
    });
    const fileRole = await request("tools/call", {
      name: "miniapp_understand_file_role",
      arguments: { projectPath: fixtureProjectPath, filePath: "miniprogram/pages/index/index.wxml" }
    });
    const outsideFile = await request("tools/call", {
      name: "miniapp_understand_file_role",
      arguments: { projectPath: fixtureProjectPath, filePath: path.join(engineRoot, "package.json") }
    });
    const yunyuContext = await request("tools/call", {
      name: "yunyu_query_context",
      arguments: { query: "客户成片展示小程序" }
    });
    const showcaseRoadmap = await request("tools/call", {
      name: "miniapp_showcase_roadmap",
      arguments: { brandName: "示例摄影工作室", depth: "mvp", phase: "all", audience: "beginner" }
    });
    const invalidEnum = await request("tools/call", {
      name: "miniapp_showcase_roadmap",
      arguments: { phase: "invalid-phase" }
    });
    const missingRequired = await request("tools/call", {
      name: "miniapp_understand_file_role",
      arguments: { projectPath: fixtureProjectPath, extraField: true }
    });
    const cliRelativePathGuard = (() => {
      try {
        validateCliToolArgs("miniapp_inspect_project", { projectPath: "relative/path" });
        return false;
      } catch {
        return true;
      }
    })();
    const devRecovery = await request("tools/call", {
      name: "miniapp_dev_recovery_playbook",
      arguments: { topic: "devtools-eisdir" }
    });
    const releasePreflight = await request("tools/call", {
      name: "miniapp_cloudbase_release_preflight",
      arguments: { action: "full-release", cloudFunctionName: "mcloud", envId: "demo-env", version: "1.2", requireHumanConfirm: false }
    });
    const validPrompt = await request("prompts/get", {
      name: "miniapp_product_manager",
      arguments: { idea: "客户成片展示小程序" }
    });
    const missingPromptArg = await request("prompts/get", {
      name: "miniapp_product_manager",
      arguments: {}
    });
    const extraPromptArg = await request("prompts/get", {
      name: "miniapp_product_manager",
      arguments: { idea: "客户成片展示小程序", extra: "no" }
    });
    const security = await request("tools/call", {
      name: "miniapp_security_quick_scan",
      arguments: { projectPath: fixtureProjectPath, limit: 220, maxFindings: 40 }
    });
    const latestLog = await request("resources/read", { uri: "miniapp://audit/optimization-log/latest" });
    const projectMapResource = await request("resources/read", { uri: "miniapp://understand/project-map" });
    const securityResource = await request("resources/read", { uri: "miniapp://audit/security-quick-scan" });
    const showcaseResource = await request("resources/read", { uri: "miniapp://roadmap/showcase" });
    const devRecoveryResource = await request("resources/read", { uri: "miniapp://playbooks/dev-recovery" });
    const preflight = await request("resources/read", { uri: "miniapp://checklists/cloudbase-release" });
    let mapJson = {};
    try {
      mapJson = JSON.parse(map.result?.content?.[0]?.text || "{}");
    } catch {}
    const edges = Array.isArray(mapJson.edges) ? mapJson.edges : [];

    return [
      assertOk("toolCount>=25", (tools.result?.tools?.length || 0) >= 25, String(tools.result?.tools?.length || 0)),
      assertOk("resourceCount>=20", (resources.result?.resources?.length || 0) >= 20, String(resources.result?.resources?.length || 0)),
      assertOk("promptCount>=3", (prompts.result?.prompts?.length || 0) >= 3, String(prompts.result?.prompts?.length || 0)),
      assertOk("has core tools", [
        "miniapp_inspect_project",
        "miniapp_generate_blueprint",
        "miniapp_project_map",
        "miniapp_relevant_context",
        "miniapp_security_quick_scan",
        "miniapp_cloudbase_release_preflight"
      ].every((name) => toolNames.includes(name))),
      assertOk("has key resources", [
        "miniapp://docs/index",
        "miniapp://checklists/launch",
        "miniapp://checklists/cloudbase-release",
        "miniapp://audit/security-quick-scan"
      ].every((uri) => resourceUris.includes(uri))),
      assertOk("has prompt workflows", [
        "miniapp_product_manager",
        "miniapp_engineering_reviewer",
        "miniapp_xiaoli_engineering_planner"
      ].every((name) => promptNames.includes(name))),
      assertOk("inspect project returns markdown", extractText(inspect).includes("工程扫描")),
      assertOk("optimization log status works", extractText(logStatus).includes("优化日志状态")),
      assertOk("project flow works", extractText(projectFlow).includes("全流程理解")),
      assertOk("relevant context works", extractText(relevantContext).includes("相关上下文")),
      assertOk("graph stats works", extractText(graphStats).includes("图谱统计")),
      assertOk("dependency diagram works", extractText(dependencyDiagram).includes("Mermaid")),
      assertOk("project map has component relations", ["uses_component", "renders_component_tag", "imports_style", "navigates_to"].every((type) => edges.some((edge) => edge.type === type))),
      assertOk("index status stays read-only", extractText(indexStatus).includes("本次是否写入缓存：否")),
      assertOk("file role shows component tags", extractText(fileRole).includes("WXML 自定义标签")),
      assertOk("outside file is rejected", outsideFile.error?.message?.includes("拒绝读取项目外文件")),
      assertOk("yunyu query requires confirmation", extractText(yunyuContext).includes("需要确认")),
      assertOk("showcase roadmap works", extractText(showcaseRoadmap).includes("客户成片展示小程序路线图")),
      assertOk("invalid enum rejected", invalidEnum.error?.code === -32602),
      assertOk("missing required rejected", missingRequired.error?.code === -32602),
      assertOk("CLI rejects relative projectPath", cliRelativePathGuard),
      assertOk("dev recovery works", extractText(devRecovery).includes("EISDIR")),
      assertOk("release preflight tool works", extractText(releasePreflight).includes("发布前预检")),
      assertOk("full release includes audit gate", extractText(releasePreflight).includes("审核发布预检")),
      assertOk("production confirm cannot be disabled", extractText(releasePreflight).includes("必须停下来确认") && extractText(releasePreflight).includes("生产动作不可关闭")),
      assertOk("valid prompt works", JSON.stringify(validPrompt.result || {}).includes("客户成片展示小程序")),
      assertOk("missing prompt arg rejected", missingPromptArg.error?.code === -32602),
      assertOk("extra prompt arg rejected", extraPromptArg.error?.code === -32602),
      assertOk("security scan returns markdown", extractText(security).includes("专项安全快扫")),
      assertOk("latest log resource works", extractText(latestLog).includes("MCP 优化日志")),
      assertOk("project map resource works", extractText(projectMapResource).includes("小程序项目地图")),
      assertOk("security scan resource works", extractText(securityResource).includes("专项安全快扫")),
      assertOk("showcase roadmap resource works", extractText(showcaseResource).includes("阶段 SOP")),
      assertOk("dev recovery resource works", extractText(devRecoveryResource).includes("故障恢复手册")),
      assertOk("release preflight resource works", extractText(preflight).includes("云函数预检"))
    ];
  });

  const summary = {
    ok: checks.every((check) => check.ok),
    fixtureProjectPath,
    checks
  };
  console.log(JSON.stringify(summary, null, 2));
  if (!summary.ok) process.exitCode = 1;
}

async function main() {
  const [command, first, second] = process.argv.slice(2);
  if (!command || command === "-h" || command === "--help") usage(0);

  if (command === "smoke" || command === "quick_validate") {
    await runSmoke();
    return;
  }

  const output = await withServer(async ({ request }) => {
    if (command === "list-tools") return request("tools/list", {});
    if (command === "call-tool") {
      if (!first) usage(1);
      return request("tools/call", { name: first, arguments: validateCliToolArgs(first, parseJsonObjectArg(second, {})) });
    }
    if (command === "list-resources") return request("resources/list", {});
    if (command === "read-resource") {
      if (!first) usage(1);
      return request("resources/read", { uri: first });
    }
    if (command === "list-prompts") return request("prompts/list", {});
    if (command === "get-prompt") {
      if (!first) usage(1);
      return request("prompts/get", { name: first, arguments: parseJsonObjectArg(second, {}) });
    }
    if (command === "index-status") {
      const args = validateCliToolArgs("miniapp_index_status", parseJsonObjectArg(first, {}));
      return request("tools/call", { name: "miniapp_index_status", arguments: args });
    }
    usage(1);
  });

  if (output?.error) {
    console.error(JSON.stringify(output.error, null, 2));
    process.exitCode = 1;
    return;
  }
  if (command.startsWith("list-") || command === "get-prompt") {
    console.log(JSON.stringify(output.result, null, 2));
  } else {
    console.log(extractText(output));
  }
}

main().catch((err) => {
  if (process.env.MINIAPP_ENGINEERING_DEBUG === "1" && err instanceof Error) {
    console.error(err.stack || err.message);
  } else {
    console.error(`Error: ${err instanceof Error ? err.message : String(err)}`);
  }
  process.exitCode = 1;
});
