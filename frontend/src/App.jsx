import { useMemo, useState } from "react";

import { readApiBaseUrl } from "./config";

const STATE_OPTIONS = [
  {
    value: "supported_answer",
    label: "Supported answer",
  },
  {
    value: "refusal",
    label: "Refusal",
  },
  {
    value: "backend_unavailable",
    label: "Backend unavailable",
  },
];

const UI_STATE_LABELS = {
  empty_input: "Empty input",
  loading: "Loading",
  supported_answer: "Supported answer",
  refusal: "Refusal",
  backend_unavailable: "Backend unavailable",
};

const SUPPORTED_ANSWER_PREVIEW = {
  final_answer:
    "A Pod is the smallest deployable unit in Kubernetes and can run one or more containers that share network and storage resources [1].",
  citations: [
    {
      marker: "[1]",
      doc_id: "content-en-docs-concepts-workloads-pods-pods",
      chunk_id: "content-en-docs-concepts-workloads-pods-pods__chunk-0001",
      start_offset: 0,
      end_offset: 118,
    },
  ],
  refusal: {
    is_refusal: false,
    reason_code: null,
    message: null,
  },
};

const REFUSAL_PREVIEW = {
  final_answer: "I can’t answer that from the approved support corpus.",
  citations: [],
  refusal: {
    is_refusal: true,
    reason_code: "no_relevant_docs",
    message: "I can’t answer that from the approved support corpus.",
  },
};

function buildPreviewState(previewMode) {
  switch (previewMode) {
    case "refusal":
      return {
        uiState: "refusal",
        result: REFUSAL_PREVIEW,
        statusText:
          "Previewing the refusal layout using final_answer plus refusal metadata from the current QueryResponse contract.",
      };
    case "backend_unavailable":
      return {
        uiState: "backend_unavailable",
        result: null,
        statusText:
          "Previewing the single backend-unavailable treatment. The thin client does not create extra error-specific states.",
      };
    default:
      return {
        uiState: "supported_answer",
        result: SUPPORTED_ANSWER_PREVIEW,
        statusText:
          "Previewing a supported answer with visible citation markers and a separate citations list.",
      };
  }
}

function ResultPanel({ uiState, result }) {
  if (uiState === "loading") {
    return (
      <div className="result-state result-state--loading" aria-live="polite">
        <p>Loading answer preview…</p>
        <div className="loading-bar" aria-hidden="true" />
      </div>
    );
  }

  if (uiState === "empty_input") {
    return (
      <div className="result-state" aria-live="polite">
        <p>Enter a question to preview the local browser shell.</p>
      </div>
    );
  }

  if (uiState === "backend_unavailable") {
    return (
      <div className="result-state result-state--error" aria-live="polite">
        <p>The backend is unavailable or incompatible right now.</p>
        <p>Retry after the API is healthy again.</p>
      </div>
    );
  }

  if (!result) {
    return null;
  }

  if (result.refusal.is_refusal) {
    return (
      <div className="result-state result-state--refusal" aria-live="polite">
        <h3>Refusal</h3>
        <p>{result.final_answer}</p>
        <dl className="result-metadata">
          <div>
            <dt>reason_code</dt>
            <dd>{result.refusal.reason_code}</dd>
          </div>
          <div>
            <dt>message</dt>
            <dd>{result.refusal.message}</dd>
          </div>
        </dl>
      </div>
    );
  }

  return (
    <div className="result-state result-state--answer" aria-live="polite">
      <h3>Supported answer</h3>
      <p>{result.final_answer}</p>
      <div className="result-subsection">
        <h4>Citations</h4>
        <ul className="citation-list">
          {result.citations.map((citation) => (
            <li key={citation.marker}>
              <strong>{citation.marker}</strong>
              <span>{citation.doc_id}</span>
              <code>{citation.chunk_id}</code>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default function App() {
  const apiBaseUrl = useMemo(() => readApiBaseUrl(), []);
  const [question, setQuestion] = useState("");
  const [previewMode, setPreviewMode] = useState("supported_answer");
  const [uiState, setUiState] = useState("empty_input");
  const [result, setResult] = useState(null);
  const [statusText, setStatusText] = useState(
    "Enter a question to preview the browser shell. No network request is sent in this scaffold yet."
  );
  const [lastSubmittedQuestion, setLastSubmittedQuestion] = useState("");

  function handleSubmit(event) {
    event.preventDefault();

    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      setUiState("empty_input");
      setResult(null);
      setStatusText("Enter a question before submitting.");
      return;
    }

    setLastSubmittedQuestion(trimmedQuestion);
    setUiState("loading");
    setResult(null);
    setStatusText(
      "Rendering the loading state. This task keeps the frontend thin and does not call /query yet."
    );

    window.setTimeout(() => {
      const preview = buildPreviewState(previewMode);
      setUiState(preview.uiState);
      setResult(preview.result);
      setStatusText(preview.statusText);
    }, 250);
  }

  return (
    <div className="app-shell">
      <header className="panel page-header">
        <p className="eyebrow">Local browser demo scaffold</p>
        <h1>SupportDoc RAG Chatbot</h1>
        <p>
          Thin React SPA shell for the frozen <code>/query</code> contract. This first
          frontend task bootstraps the page layout only.
        </p>
      </header>

      <main className="page-grid">
        <section className="panel">
          <h2>Question box</h2>
          <form className="question-form" onSubmit={handleSubmit}>
            <label htmlFor="question-input">Question</label>
            <textarea
              id="question-input"
              name="question"
              rows="5"
              placeholder="What is a Pod?"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
            />
            <p className="helper-text">
              The browser trims whitespace before submit and blocks empty input locally.
            </p>

            <fieldset className="preview-fieldset">
              <legend>Placeholder layout preview</legend>
              {STATE_OPTIONS.map((option) => (
                <label key={option.value} className="preview-option">
                  <input
                    checked={previewMode === option.value}
                    name="preview-state"
                    type="radio"
                    value={option.value}
                    onChange={(event) => setPreviewMode(event.target.value)}
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </fieldset>

            <div className="form-actions">
              <button type="submit" disabled={uiState === "loading"}>
                {uiState === "loading" ? "Loading…" : "Submit"}
              </button>
            </div>
          </form>
        </section>

        <section className="panel">
          <h2>Result panel</h2>
          <ResultPanel uiState={uiState} result={result} />
        </section>
      </main>

      <aside className="panel status-panel">
        <h2>Status area</h2>
        <div className="status-grid">
          <div>
            <span className="status-label">UI state</span>
            <strong>{UI_STATE_LABELS[uiState]}</strong>
          </div>
          <div>
            <span className="status-label">Configured API base URL</span>
            <code>{apiBaseUrl}</code>
          </div>
          <div>
            <span className="status-label">Last submitted question</span>
            <span>{lastSubmittedQuestion || "None yet"}</span>
          </div>
        </div>
        <p className="status-message">{statusText}</p>
      </aside>
    </div>
  );
}
