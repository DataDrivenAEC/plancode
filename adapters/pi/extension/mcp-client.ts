// Minimal MCP client over stdio (newline-delimited JSON-RPC 2.0): enough to drive the arch-harness server.
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createInterface } from "node:readline";

export interface McpTool { name: string; description: string; inputSchema: Record<string, unknown> }
export interface McpResult { content: { type: string; text: string }[]; isError: boolean; structuredContent?: any }

export class McpClient {
  private proc: ChildProcessWithoutNullStreams;
  private next = 0;
  private pending = new Map<number, { resolve: (v: any) => void; reject: (e: Error) => void }>();
  private stderr = "";

  constructor(command: string, args: string[], cwd: string) {
    this.proc = spawn(command, args, { cwd, stdio: ["pipe", "pipe", "pipe"] });
    createInterface({ input: this.proc.stdout }).on("line", line => {
      if (!line.trim()) return;
      const msg = JSON.parse(line);
      const p = this.pending.get(msg.id);
      if (!p) return;
      this.pending.delete(msg.id);
      this.hold(this.pending.size > 0);
      msg.error ? p.reject(new Error(`${msg.error.code}: ${msg.error.message}`)) : p.resolve(msg.result);
    });
    this.proc.stderr.on("data", d => { this.stderr = (this.stderr + d).slice(-4000); });
    this.hold(false);
    this.proc.on("exit", code => {
      for (const p of this.pending.values()) p.reject(new Error(`arch-harness MCP server exited (${code}): ${this.stderr}`));
      this.pending.clear();
    });
  }

  // Keep the host process alive only while a request is in flight: an idle server never blocks pi from exiting
  // (the server ends by itself when its stdin closes).
  private hold(on: boolean) {
    for (const h of [this.proc, this.proc.stdin, this.proc.stdout, this.proc.stderr] as any[]) on ? h.ref?.() : h.unref?.();
  }

  request(method: string, params: Record<string, unknown> = {}): Promise<any> {
    const id = ++this.next;
    this.hold(true);
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n");
    });
  }

  async initialize(): Promise<McpTool[]> {
    await this.request("initialize", { protocolVersion: "2025-06-18", capabilities: {},
      clientInfo: { name: "arch-harness-pi", version: "0.0.1" } });
    this.proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) + "\n");
    return (await this.request("tools/list")).tools;
  }

  call(name: string, args: Record<string, unknown> = {}): Promise<McpResult> {
    return this.request("tools/call", { name, arguments: args });
  }

  close() { this.proc.stdin.end(); this.proc.kill(); }
}
