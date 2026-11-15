import { execFile } from "node:child_process";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { promisify } from "node:util";
import { expect, test } from "vitest";

const execute = promisify(execFile);

test.each([false, true])(
  "load test cleans its ideas, including when a read fails (%s)",
  async (failRead) => {
    const ideas = new Set<string>();
    let nextId = 0;
    const server = createServer((request, response) => {
      if (request.method === "POST") {
        const id = String(++nextId);
        ideas.add(id);
        response.writeHead(201, { "Content-Type": "application/json" });
        response.end(JSON.stringify({ id }));
      } else if (request.method === "DELETE") {
        ideas.delete(request.url!.split("/").at(-1)!);
        response.writeHead(204).end();
      } else {
        response.writeHead(failRead ? 503 : 200, {
          "Content-Type": "application/json",
        });
        response.end("[]");
      }
    });
    await new Promise<void>((resolve) =>
      server.listen(0, "127.0.0.1", resolve),
    );
    try {
      const address = server.address() as AddressInfo;
      const result = await execute(process.execPath, ["tests/load.mjs"], {
        env: {
          ...process.env,
          IDEA_BOARD_BASE_URL: `http://127.0.0.1:${address.port}`,
          LOAD_CYCLES: "6",
          LOAD_CONCURRENCY: "2",
        },
      }).catch((error: { code: number; stdout: string }) => ({
        stdout: error.stdout,
        code: error.code,
      }));
      const report = JSON.parse(result.stdout);
      expect(report.requests).toBe(18);
      expect(report.failedRequests).toBe(failRead ? 6 : 0);
      expect(report.failedCycles).toBe(failRead ? 6 : 0);
      expect(report.cleanupFailures).toBe(0);
      expect(ideas.size).toBe(0);
      if (failRead) expect("code" in result && result.code).toBe(1);
    } finally {
      await new Promise<void>((resolve, reject) =>
        server.close((error) => (error ? reject(error) : resolve())),
      );
    }
  },
);
