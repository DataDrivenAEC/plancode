// arch-harness adapter for pi: the hook contract on pi's events; the domain stays in the Python MCP server.
//   before_agent_start   -> ah_context        DESIGN.md and status into the system prompt
//   tool_result          -> ah_after_step     rules after every generator call, failures appended to the result
//   agent_before_settle  -> ah_before_settle  no settling while rules fail (bounded; says why when it gives up)
//   session fork, /variant -> ah_fork_variant a variant on its own git branch
// Config: AH_PYTHON (default <repo>/.conda-ah/bin/python), AH_PROJECT (default cwd), AH_MAX_ROUNDS (default 5).
import path from "node:path";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { McpClient } from "./mcp-client.ts";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const GENERATORS = new Set(["generate_massing", "run_loop"]);   // tools that change the model
const HARNESS_ONLY = new Set(["ah_context", "ah_after_step", "ah_before_settle", "ah_fork_variant"]);
const text = (r: { content: { text: string }[] }) => r.content.map(c => c.text).join("\n");

export default function archHarness(pi: ExtensionAPI) {
  let client: McpClient | undefined;
  let ready: Promise<void> | undefined;
  let runStartRound = 0;
  let holds = 0;
  const registered = new Set<string>();
  const maxRounds = () => Number(process.env.AH_MAX_ROUNDS ?? 5);

  function start(cwd: string): Promise<void> {
    if (ready) return ready;
    const project = path.resolve(process.env.AH_PROJECT ?? cwd);
    const local = path.join(REPO, ".conda-ah/bin/python");
    const python = process.env.AH_PYTHON ?? (existsSync(local) ? local : "python3");
    client = new McpClient(python, ["-m", "arch_harness.mcp_server", "--project", project], REPO);
    ready = client.initialize().then(tools => {
      for (const t of tools) {
        if (HARNESS_ONLY.has(t.name) || registered.has(t.name)) continue;
        registered.add(t.name);
        pi.registerTool({
          name: t.name, label: t.name, description: t.description,
          parameters: Type.Unsafe<Record<string, unknown>>(t.inputSchema),
          async execute(_id, params) {
            const r = await client!.call(t.name, params as Record<string, unknown>);
            if (r.isError) throw new Error(text(r));
            return { content: [{ type: "text", text: text(r) }], details: r.structuredContent };
          },
        });
      }
    });
    return ready;
  }

  pi.on("session_start", async (event, ctx) => {
    await start(ctx.cwd);
    if (event.reason === "fork") {   // a forked session is a design variant: give it its own branch
      const name = `fork-${Date.now().toString(36)}`;
      const r = await client!.call("ah_fork_variant", { name });
      if (ctx.hasUI) ctx.ui.notify(text(r), "info");
    }
  });

  pi.on("before_agent_start", async (event, ctx) => {
    await start(ctx.cwd);
    const r = await client!.call("ah_context");
    runStartRound = r.structuredContent?.rounds ?? 0;
    holds = 0;
    event.systemPromptOptions.sections = { ...(event.systemPromptOptions.sections ?? {}), "arch-harness": text(r) };
  });

  pi.on("tool_result", async event => {
    if (!GENERATORS.has(event.toolName) || event.isError || !client) return;
    const step = await client.call("ah_after_step");
    return { content: [...event.content, { type: "text", text: text(step) }] };
  });

  pi.on("agent_before_settle", async () => {
    if (!client) return;
    const status = (await client.call("ah_context")).structuredContent;
    if (!status || status.rounds <= runStartRound) return;   // no generator step this run: nothing to hold
    const r = await client.call("ah_before_settle", { max_rounds: maxRounds(), since_round: runStartRound });
    const out = r.structuredContent as { settle: boolean; reason: string };
    if (!out.settle && holds < maxRounds()) {
      holds += 1;
      return { continue: true, entries: [{ type: "custom_message", customType: "arch-harness", display: true,
        content: `arch-harness: ${out.reason}` }] };
    }
    const reason = out.settle ? out.reason : `cannot converge: stopped after ${holds} hold(s); ${out.reason}`;
    if (reason.startsWith("all three")) return;
    return { entries: [{ type: "custom_message", customType: "arch-harness", display: true,
      content: `arch-harness: ${reason}` }] };
  });

  pi.registerCommand("variant", {
    description: "Put the design on its own git branch: /variant <name>",
    handler: async (args, ctx) => {
      await start(ctx.cwd);
      const name = args.trim();
      if (!/^[a-z0-9][a-z0-9-]*$/.test(name)) return ctx.ui.notify("Usage: /variant <name> (a-z, 0-9, -)", "warning");
      ctx.ui.notify(text(await client!.call("ah_fork_variant", { name })), "info");
    },
  });

  pi.on("session_shutdown", () => { client?.close(); client = undefined; ready = undefined; });
}
