import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import test from "node:test";

const baseUrl = process.env.IDEA_BOARD_BASE_URL ?? "http://127.0.0.1:3000";

test("serves the web app and reads and writes ideas through its API proxy", async () => {
  const index = await fetch(baseUrl);
  assert.equal(index.status, 200);
  assert.match(index.headers.get("content-type"), /text\/html/);
  const html = await index.text();
  assert.match(html, /<title>Idea Board<\/title>/);
  const assetPath = html.match(/src="(\/assets\/[^\"]+\.js)"/)?.[1];
  assert.ok(assetPath, "HTML must reference the built application");
  const asset = await fetch(new URL(assetPath, baseUrl));
  assert.equal(asset.status, 200);
  assert.match(asset.headers.get("content-type"), /javascript/);
  assert.match(asset.headers.get("cache-control"), /immutable/);

  const content = `Stack check ${randomUUID()}`;
  const created = [];
  for (const text of [content, `${content} second`]) {
    const response = await fetch(new URL("/api/ideas", baseUrl), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text }),
    });
    assert.equal(response.status, 201);
    const idea = await response.json();
    assert.equal(idea.content, text);
    assert.equal(typeof idea.id, "string");
    created.push(idea);
  }

  const firstPage = await fetch(new URL("/api/ideas?limit=1", baseUrl));
  assert.equal(firstPage.status, 200);
  assert.deepEqual(await firstPage.json(), [created[1]]);
  const nextPath = firstPage.headers
    .get("link")
    ?.match(/^<([^>]+)>; rel="next"$/)?.[1];
  assert.ok(nextPath, "The next-page link must survive the proxy");
  const secondPage = await fetch(new URL(nextPath, baseUrl));
  assert.equal(secondPage.status, 200);
  assert.deepEqual(await secondPage.json(), [created[0]]);

  const invalid = await fetch(new URL("/api/ideas", baseUrl), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content: " " }),
  });
  assert.equal(invalid.status, 422);
  const duplicate = await fetch(new URL("/api/ideas", baseUrl), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content: `  ${content}  ` }),
  });
  assert.equal(duplicate.status, 409);
  for (const idea of created) {
    const removed = await fetch(new URL(`/api/ideas/${idea.id}`, baseUrl), {
      method: "DELETE",
    });
    assert.equal(removed.status, 204);
    assert.equal(await removed.text(), "");
  }
  const missing = await fetch(new URL(`/api/ideas/${created[0].id}`, baseUrl), {
    method: "DELETE",
  });
  assert.equal(missing.status, 404);
  const remaining = await fetch(new URL("/api/ideas?limit=50", baseUrl));
  const ideas = await remaining.json();
  assert.ok(
    created.every((removed) => !ideas.some((idea) => idea.id === removed.id)),
  );
});
