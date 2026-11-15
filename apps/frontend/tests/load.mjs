import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { performance } from "node:perf_hooks";

function integer(name, fallback, maximum) {
  const value = process.env[name] ?? String(fallback);
  assert.match(value, /^[1-9]\d*$/, `${name} must be a positive integer`);
  const number = Number(value);
  assert.ok(number <= maximum, `${name} must be at most ${maximum}`);
  return number;
}

const baseUrl = process.env.IDEA_BOARD_BASE_URL ?? "http://127.0.0.1:3000";
const concurrency = integer("LOAD_CONCURRENCY", 10, 100);
const cycles = integer("LOAD_CYCLES", 100, 100000);
const latencyLimit = process.env.LOAD_MAX_P95_MS
  ? integer("LOAD_MAX_P95_MS", 1, 3600000)
  : null;
const latencies = [];
const errors = [];
let failedRequests = 0;
let failedCycles = 0;
let cleanupFailures = 0;
let nextCycle = 0;

async function request(method, path, content) {
  const started = performance.now();
  try {
    const response = await fetch(new URL(path, baseUrl), {
      method,
      headers: { "Content-Type": "application/json" },
      body: content === undefined ? undefined : JSON.stringify(content),
      signal: AbortSignal.timeout(10000),
    });
    const expected = method === "POST" ? 201 : method === "DELETE" ? 204 : 200;
    assert.equal(
      response.status,
      expected,
      `${method} ${path}: unexpected status`,
    );
    return response.status === 204 ? null : await response.json();
  } catch (error) {
    failedRequests++;
    throw error;
  } finally {
    latencies.push(performance.now() - started);
  }
}

async function worker() {
  while (nextCycle < cycles) {
    const cycle = nextCycle++;
    let created;
    try {
      created = await request("POST", "/api/ideas", {
        content: `Load check ${randomUUID()} cycle ${cycle}`,
      });
      assert.equal(typeof created.id, "string");
      const listed = await request("GET", "/api/ideas?limit=1");
      assert.ok(Array.isArray(listed));
    } catch (error) {
      failedCycles++;
      if (errors.length < 10) errors.push(String(error));
    } finally {
      if (created?.id) {
        try {
          await request(
            "DELETE",
            `/api/ideas/${encodeURIComponent(created.id)}`,
          );
        } catch (error) {
          cleanupFailures++;
          if (errors.length < 10) errors.push(`Cleanup: ${String(error)}`);
        }
      }
    }
  }
}

const started = performance.now();
await Promise.all(
  Array.from({ length: Math.min(concurrency, cycles) }, worker),
);
const elapsed = (performance.now() - started) / 1000;
latencies.sort((left, right) => left - right);
const p95 = latencies[Math.ceil(latencies.length * 0.95) - 1];
console.log(
  JSON.stringify(
    {
      cycles,
      concurrency,
      requests: latencies.length,
      failedRequests,
      failedCycles,
      cleanupFailures,
      elapsedSeconds: Number(elapsed.toFixed(3)),
      requestsPerSecond: Number((latencies.length / elapsed).toFixed(2)),
      p95RequestMs: Number(p95.toFixed(2)),
      latencyLimitMs: latencyLimit,
      errors,
    },
    null,
    2,
  ),
);
if (
  failedCycles ||
  failedRequests ||
  cleanupFailures ||
  (latencyLimit !== null && p95 > latencyLimit)
) {
  process.exitCode = 1;
}
