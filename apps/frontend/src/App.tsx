import { useEffect, useState, type FormEvent } from "react";
import { deleteIdea, listIdeas, submitIdea, type Idea } from "./api";

const dateFormat = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

export default function App() {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [draft, setDraft] = useState("");
  const [nextId, setNextId] = useState<string>();
  const [loading, setLoading] = useState<"initial" | "more" | null>("initial");
  const [loadError, setLoadError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [deleteId, setDeleteId] = useState<string>();
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const content = draft.trim();
  const characterCount = Array.from(content).length;
  const invalid = !content || characterCount > 2000 || content.includes("\0");

  async function load(beforeId?: string, signal?: AbortSignal) {
    setLoading(beforeId ? "more" : "initial");
    if (!beforeId) setNextId(undefined);
    setLoadError("");
    try {
      const page = await listIdeas(beforeId, signal);
      if (signal?.aborted) return;
      setIdeas((current) =>
        beforeId
          ? [
              ...current,
              ...page.ideas.filter(
                (idea) => !current.some((item) => item.id === idea.id),
              ),
            ]
          : page.ideas,
      );
      setNextId(page.nextId);
    } catch {
      if (!signal?.aborted)
        setLoadError("Couldn’t load ideas. Please try again.");
    } finally {
      if (!signal?.aborted) setLoading(null);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    void load(undefined, controller.signal);
    return () => controller.abort();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (invalid || submitting || loading === "initial") return;
    setSubmitting(true);
    setSubmitError("");
    setSubmitted(false);
    try {
      const idea = await submitIdea(content);
      if (idea === null) {
        setSubmitError("That idea is already on the board.");
        return;
      }
      setIdeas((current) => [
        idea,
        ...current.filter((item) => item.id !== idea.id),
      ]);
      setDraft("");
      setSubmitted(true);
    } catch {
      setSubmitError(
        "Couldn’t confirm your submission. Your text is still here. Refresh the ideas before trying again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function remove(id: string) {
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteIdea(id);
      setIdeas((current) => current.filter((idea) => idea.id !== id));
      setDeleteId(undefined);
    } catch {
      setDeleteError(
        "Couldn’t confirm deletion. Refresh the ideas to check the board.",
      );
    } finally {
      setDeleting(false);
    }
  }

  return (
    <main>
      <header className="page-header">
        <a className="brand" href="/" aria-label="Idea Board home">
          <span className="brand-mark" aria-hidden="true">
            ✳
          </span>
          Idea Board
        </a>
        <span className="header-note">A little space for what’s next.</span>
      </header>

      <section className="intro" aria-labelledby="page-title">
        <p className="eyebrow">THINK IT. WRITE IT. SHARE IT.</p>
        <h1 id="page-title">
          Good things start
          <br />
          with an idea.
        </h1>
        <p className="intro-copy">
          A small improvement. A big what-if. Put it on the board.
        </p>
      </section>

      <div className="board-layout">
        <section className="composer" aria-labelledby="composer-title">
          <span className="section-number" aria-hidden="true">
            01 / CONTRIBUTE
          </span>
          <h2 id="composer-title">What’s on your mind?</h2>
          <form onSubmit={submit}>
            <label htmlFor="idea">Your idea</label>
            <textarea
              id="idea"
              placeholder="What could we make better?"
              value={draft}
              onChange={(event) => {
                setDraft(event.target.value);
                setSubmitted(false);
                setSubmitError("");
              }}
              disabled={submitting}
              aria-describedby="idea-hint idea-count"
              aria-invalid={characterCount > 2000 || content.includes("\0")}
              rows={6}
              required
            />
            <div className="field-details">
              <span id="idea-hint">A few words are enough.</span>
              <span
                id="idea-count"
                className={characterCount > 2000 ? "over-limit" : ""}
              >
                {characterCount.toLocaleString()} / 2,000
              </span>
            </div>
            <button
              className="submit-button"
              disabled={invalid || submitting || loading === "initial"}
            >
              {submitting ? "Adding idea…" : "Add to the board"}
              <span aria-hidden="true">↗</span>
            </button>
            {submitError && (
              <p className="error" role="alert">
                {submitError}
              </p>
            )}
            {submitted && (
              <p className="success" role="status">
                Your idea is on the board.
              </p>
            )}
          </form>
          <p className="composer-note">Shared here, visible to everyone.</p>
        </section>

        <section
          className="ideas-section"
          aria-labelledby="ideas-title"
          aria-busy={loading !== null}
        >
          <div className="list-header">
            <div>
              <span className="section-number" aria-hidden="true">
                02 / THE BOARD
              </span>
              <h2 id="ideas-title">Fresh perspectives</h2>
            </div>
            <div className="list-actions">
              <span className="sort-label">Newest first ↓</span>
              <button
                className="refresh-button"
                onClick={() => void load()}
                disabled={loading !== null || submitting || deleting}
              >
                Refresh ideas
              </button>
            </div>
          </div>

          {loading === "initial" && (
            <p className="empty-state" role="status">
              Loading the board…
            </p>
          )}
          {!loading && !loadError && ideas.length === 0 && (
            <div className="empty-state">
              <span className="empty-mark" aria-hidden="true">
                ✳
              </span>
              <h3>A blank board. Plenty of possibility.</h3>
              <p>Share the first idea to get things going.</p>
            </div>
          )}

          <ol className="idea-list">
            {ideas.map((idea) => (
              <li key={idea.id} className="idea-card">
                <div className="idea-meta">
                  <span className="idea-id">
                    IDEA / {idea.id.padStart(3, "0")}
                  </span>
                  <time dateTime={idea.created_at}>
                    {dateFormat.format(new Date(idea.created_at))}
                  </time>
                </div>
                <p>{idea.content}</p>
                <div className="idea-actions">
                  {deleteId === idea.id ? (
                    <>
                      <span>Delete this idea?</span>
                      <button
                        className="delete-button"
                        onClick={() => void remove(idea.id)}
                        disabled={deleting || loading !== null}
                      >
                        {deleting ? "Deleting…" : "Delete idea"}
                      </button>
                      <button
                        className="cancel-button"
                        onClick={() => setDeleteId(undefined)}
                        disabled={deleting}
                      >
                        Cancel
                      </button>
                      {deleteError && (
                        <span className="error" role="alert">
                          {deleteError}
                        </span>
                      )}
                    </>
                  ) : (
                    <button
                      className="delete-button"
                      aria-label={`Delete idea ${idea.id}`}
                      onClick={() => {
                        setDeleteId(idea.id);
                        setDeleteError("");
                      }}
                      disabled={deleting || loading !== null}
                    >
                      Delete
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ol>

          {loadError && (
            <p className="error" role="alert">
              {loadError}
            </p>
          )}
          {(nextId || loadError) && (
            <button
              className="load-button"
              onClick={() => void load(nextId)}
              disabled={loading !== null || deleting}
            >
              {loading === "more"
                ? "Loading…"
                : loadError
                  ? "Try again"
                  : "Load more ideas"}
            </button>
          )}
        </section>
      </div>
      <footer>Room for the next good idea.</footer>
    </main>
  );
}
