import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import type { Idea } from "../src/api";

const idea: Idea = {
  id: "9007199254740993",
  content: "Make deployments easier to investigate",
  created_at: "2026-11-13T10:00:00Z",
};
const fetchMock = vi.fn<typeof fetch>();

function page(ideas: Idea[] = [], nextId?: string) {
  return new Response(JSON.stringify(ideas), {
    headers: nextId
      ? { Link: `</api/ideas?limit=50&before_id=${nextId}>; rel="next"` }
      : {},
  });
}

async function openBoard() {
  render(<App />);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Refresh ideas" })).toBeEnabled(),
  );
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

describe("Idea Board", () => {
  it("loads the first bounded page and shows the empty state", async () => {
    fetchMock.mockResolvedValueOnce(page());
    await openBoard();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/ideas?limit=50",
      expect.any(Object),
    );
    expect(
      screen.getByText("A blank board. Plenty of possibility."),
    ).toBeVisible();
  });

  it("renders submitted HTML as text and preserves large IDs", async () => {
    fetchMock.mockResolvedValueOnce(
      page([{ ...idea, content: '<script>alert("hi")</script>' }]),
    );
    await openBoard();
    expect(screen.getByText('<script>alert("hi")</script>')).toBeVisible();
    expect(document.querySelector(".idea-card script")).toBeNull();
    expect(screen.getByText(`IDEA / ${idea.id}`)).toBeVisible();
    expect(document.querySelector("time")).toHaveAttribute(
      "datetime",
      idea.created_at,
    );
  });

  it("trims a submission and adds the confirmed result first", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(page([idea]));
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          ...idea,
          id: "9007199254740994",
          content: "A useful idea",
        }),
        { status: 201 },
      ),
    );
    await openBoard();
    await user.type(screen.getByLabelText("Your idea"), "  A useful idea  ");
    await user.click(screen.getByRole("button", { name: "Add to the board" }));
    await screen.findByText("Your idea is on the board.");
    expect(fetchMock).toHaveBeenLastCalledWith("/api/ideas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: "A useful idea" }),
    });
    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent(
      "A useful idea",
    );
    expect(screen.getByLabelText("Your idea")).toHaveValue("");
  });

  it("keeps a failed draft and lets the user check the board without resubmitting", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(page());
    fetchMock.mockRejectedValueOnce(new TypeError("Network error"));
    fetchMock.mockResolvedValueOnce(page());
    await openBoard();
    await user.type(screen.getByLabelText("Your idea"), "Keep this draft");
    await user.click(screen.getByRole("button", { name: "Add to the board" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn’t confirm your submission",
    );
    await user.click(screen.getByRole("button", { name: "Refresh ideas" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(screen.getByLabelText("Your idea")).toHaveValue("Keep this draft");
    expect(
      fetchMock.mock.calls.filter(([, options]) => options?.method === "POST"),
    ).toHaveLength(1);
  });

  it("does not show an unconfirmed idea and disables repeated submits while saving", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(page());
    let finish!: (response: Response) => void;
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    await openBoard();
    await user.type(
      screen.getByLabelText("Your idea"),
      "Wait for confirmation",
    );
    await user.click(screen.getByRole("button", { name: "Add to the board" }));
    expect(screen.getByRole("button", { name: "Adding idea…" })).toBeDisabled();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
    finish(new Response("Unavailable", { status: 503 }));
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.getByLabelText("Your idea")).toHaveValue(
      "Wait for confirmation",
    );
  });

  it("retries an initial read failure", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(
      new Response("Unavailable", { status: 503 }),
    );
    fetchMock.mockResolvedValueOnce(page([idea]));
    await openBoard();
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn’t load ideas");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(idea.content)).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("keeps loaded ideas when an older-page read fails and retries the same cursor", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(page([idea], idea.id));
    fetchMock.mockRejectedValueOnce(new TypeError("Network error"));
    fetchMock.mockResolvedValueOnce(
      page([idea, { ...idea, id: "1", content: "An older idea" }]),
    );
    await openBoard();
    await user.click(screen.getByRole("button", { name: "Load more ideas" }));
    await screen.findByRole("alert");
    expect(screen.getByText(idea.content)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("An older idea")).toBeVisible();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(fetchMock.mock.calls[1][0]).toBe(
      `/api/ideas?limit=50&before_id=${idea.id}`,
    );
    expect(fetchMock.mock.calls[2][0]).toBe(fetchMock.mock.calls[1][0]);
    expect(
      screen.queryByRole("button", { name: "Load more ideas" }),
    ).not.toBeInTheDocument();
  });

  it("rejects blank and oversized content while counting emoji as characters", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(page());
    await openBoard();
    const field = screen.getByLabelText("Your idea");
    const button = screen.getByRole("button", { name: "Add to the board" });
    await user.type(field, "   ");
    expect(button).toBeDisabled();
    await user.clear(field);
    await user.click(field);
    await user.paste("💡".repeat(2000));
    expect(button).toBeEnabled();
    expect(screen.getByText("2,000 / 2,000")).toBeVisible();
    await user.paste("x");
    expect(button).toBeDisabled();
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("shows a duplicate message and keeps the draft", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(page([idea]));
    fetchMock.mockResolvedValueOnce(new Response("Conflict", { status: 409 }));
    await openBoard();
    await user.type(screen.getByLabelText("Your idea"), idea.content);
    await user.click(screen.getByRole("button", { name: "Add to the board" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That idea is already on the board.",
    );
    expect(screen.getByLabelText("Your idea")).toHaveValue(idea.content);
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("lets the user cancel deletion without calling the API", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(page([idea]));
    await openBoard();
    await user.click(
      screen.getByRole("button", { name: `Delete idea ${idea.id}` }),
    );
    expect(screen.getByText("Delete this idea?")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByText(idea.content)).toBeVisible();
    expect(screen.queryByText("Delete this idea?")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("removes an idea only after deletion succeeds", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(page([idea]));
    let finish!: (response: Response) => void;
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    await openBoard();
    await user.click(
      screen.getByRole("button", { name: `Delete idea ${idea.id}` }),
    );
    await user.click(screen.getByRole("button", { name: "Delete idea" }));
    expect(screen.getByRole("button", { name: "Deleting…" })).toBeDisabled();
    expect(screen.getByText(idea.content)).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Refresh ideas" }),
    ).toBeDisabled();
    finish(new Response(null, { status: 204 }));
    await waitFor(() =>
      expect(screen.queryByText(idea.content)).not.toBeInTheDocument(),
    );
    expect(fetchMock).toHaveBeenLastCalledWith(`/api/ideas/${idea.id}`, {
      method: "DELETE",
    });
  });

  it("keeps an idea visible when deletion fails", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(page([idea]));
    fetchMock.mockResolvedValueOnce(
      new Response("Unavailable", { status: 503 }),
    );
    await openBoard();
    await user.click(
      screen.getByRole("button", { name: `Delete idea ${idea.id}` }),
    );
    await user.click(screen.getByRole("button", { name: "Delete idea" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn’t confirm deletion",
    );
    expect(screen.getByText(idea.content)).toBeVisible();
  });

  it("removes a stale idea when another client already deleted it", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(page([idea]));
    fetchMock.mockResolvedValueOnce(new Response("Not found", { status: 404 }));
    await openBoard();
    await user.click(
      screen.getByRole("button", { name: `Delete idea ${idea.id}` }),
    );
    await user.click(screen.getByRole("button", { name: "Delete idea" }));
    await waitFor(() =>
      expect(screen.queryByText(idea.content)).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
