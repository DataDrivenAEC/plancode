// Offline test of the pi adapter: a real pi session (SDK) with pi's faux provider standing in for the model.
// Run: .tools/node/bin/node --test adapters/pi/test/adapter.test.ts   (needs .conda-ah for the MCP server)
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../../..");
const python = path.join(repo, ".conda-ah/bin/python");
const extension = path.resolve(here, "../extension/index.ts");
const pi = await import("@earendil-works/pi-coding-agent");
const piAi = await import(pathToFileURL(path.join(repo,
  "node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-ai/dist/index.js")).href);

function newProject(example: string): string {
  const dir = mkdtempSync(path.join(tmpdir(), "ah-pi-"));
  rmSync(dir, { recursive: true });
  execFileSync(python, ["-m", "arch_harness", "init", "--example", example, "--out", dir], { cwd: repo });
  return dir;
}

async function openSession(project: string, responses: unknown[]) {
  const agentDir = mkdtempSync(path.join(tmpdir(), "ah-pi-agent-"));
  const modelRuntime = await pi.ModelRuntime.create({ authPath: path.join(agentDir, "auth.json"), modelsPath: null,
    refreshOnCreate: false });
  const faux = piAi.fauxProvider({ provider: "faux" });
  modelRuntime.registerNativeProvider(faux.provider);
  faux.setResponses(responses);
  const settingsManager = pi.SettingsManager.inMemory();
  const resourceLoader = new pi.DefaultResourceLoader({ cwd: project, agentDir, settingsManager,
    additionalExtensionPaths: [extension], noContextFiles: true, noPromptTemplates: true, noThemes: true });
  await resourceLoader.reload();
  const { session } = await pi.createAgentSession({ cwd: project, agentDir, modelRuntime, model: faux.getModel(),
    resourceLoader, settingsManager, sessionManager: pi.SessionManager.inMemory(project), noTools: "builtin" });
  return { session, faux };
}

const text = (ctx: unknown) => JSON.stringify(ctx);
const rounds = (project: string) =>
  readdirSync(path.join(project, "model/rounds")).sort().map(f =>
    JSON.parse(readFileSync(path.join(project, "model/rounds", f), "utf8")));
const custom = (s: any) => s.messages.filter((m: any) => m.role === "custom" && m.customType === "arch-harness");

test("design loop: DESIGN.md in context, rules after each step, settling held while rules fail", async () => {
  process.env.AH_MAX_ROUNDS = "5";
  const project = newProject("clinic");
  let sawDesign = false;
  const { session, faux } = await openSession(project, [
    (ctx: unknown) => { sawDesign = text(ctx).includes("Neighbourhood health clinic");
      return piAi.fauxAssistantMessage(piAi.fauxToolCall("generate_massing", {}), { stopReason: "toolUse" }); },
    piAi.fauxAssistantMessage("Done."),   // premature: the rules still fail
    (ctx: unknown) => {
      const m = /Deterministic fixes \(apply as overrides\): ([^"\\]+)/.exec(text(ctx));
      assert.ok(m, "the failures and fixes reached the model");
      const overrides = Object.fromEntries(m[1].split(", ").map(p => {
        const [k, v] = p.split(" "); return [k, Number(v.split("→")[1])]; }));
      return piAi.fauxAssistantMessage(piAi.fauxToolCall("generate_massing", { overrides }), { stopReason: "toolUse" });
    },
    piAi.fauxAssistantMessage("All three rule kinds pass."),
  ]);
  try {
    await session.prompt("Design the clinic.");
    assert.equal(sawDesign, true);
    assert.equal(faux.state.callCount, 4);
    const r = rounds(project);
    assert.equal(r.length, 2);
    assert.equal(r[0].passed, false);
    assert.equal(r[1].passed, true);
    assert.ok(custom(session).some((m: any) => String(m.content).includes("rules still fail")));
  } finally { session.dispose(); }
});

test("cannot converge: settles with the reason instead of claiming success", async () => {
  process.env.AH_MAX_ROUNDS = "1";
  const project = newProject("tight-site");
  const { session, faux } = await openSession(project, [
    piAi.fauxAssistantMessage(piAi.fauxToolCall("generate_massing", {}), { stopReason: "toolUse" }),
    piAi.fauxAssistantMessage("Here is the design."),
  ]);
  try {
    await session.prompt("Design the clinic on the tight site.");
    assert.equal(faux.state.callCount, 2);
    const msgs = custom(session).map((m: any) => String(m.content));
    assert.ok(msgs.some(c => c.startsWith("arch-harness: cannot converge")), msgs.join("\n"));
  } finally { session.dispose(); }
});

test("/variant puts the design on its own git branch", async () => {
  const project = newProject("clinic");
  const { session } = await openSession(project, []);
  try {
    await session.prompt("/variant timber");
    const branch = execFileSync("git", ["-C", project, "branch", "--show-current"]).toString().trim();
    assert.equal(branch, "variant/timber");
    assert.ok(existsSync(path.join(project, "DESIGN.md")));
  } finally { session.dispose(); }
});
