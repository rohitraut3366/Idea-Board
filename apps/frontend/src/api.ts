export interface Idea {
  id: string;
  content: string;
  created_at: string;
}

export async function listIdeas(beforeId?: string, signal?: AbortSignal) {
  const query = new URLSearchParams({ limit: "50" });
  if (beforeId) query.set("before_id", beforeId);

  const response = await fetch(`/api/ideas?${query}`, { signal });
  if (!response.ok) throw new Error("Couldn’t load ideas. Please try again.");

  const ideas: Idea[] = await response.json();
  const nextId = response.headers
    .get("Link")
    ?.match(/before_id=(\d+)>; rel="next"/)?.[1];
  return { ideas, nextId };
}

export async function submitIdea(content: string): Promise<Idea | null> {
  const response = await fetch("/api/ideas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (response.status === 409) return null;
  if (!response.ok) throw new Error("Submission could not be confirmed.");
  return response.json();
}

export async function deleteIdea(id: string): Promise<void> {
  const response = await fetch(`/api/ideas/${id}`, { method: "DELETE" });
  if (!response.ok && response.status !== 404) {
    throw new Error("Deletion could not be confirmed.");
  }
}
