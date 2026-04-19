import { Fragment, useCallback, useEffect, useMemo, useState } from "react";

import { buildApiUrl, readApiBaseUrl } from "./config";

const UI_STATE_LABELS = {
  empty_input: "Empty input",
  loading: "Loading",
  supported_answer: "Supported answer",
  refusal: "Refusal",
  backend_unavailable: "Backend unavailable",
};

const BACKEND_STATUS_LABELS = {
  checking: "Checking",
  ready: "Ready",
  unavailable: "Unavailable",
  incompatible: "Incompatible",
};

const READINESS_TIMEOUT_MS = 10000;
const QUERY_TIMEOUT_MS = 120000;
const CITATION_MARKER_PATTERN = /(\[\d+\])/g;

const INITIAL_BACKEND_STATUS = {
  state: "checking",
  service: null,
  environment: null,
  version: null,
  queryContract: null,
  message: "Checking backend readiness via /readyz.",
};

function isCitationMarkerSegment(segment) {
  return /^\[\d+\]$/.test(segment);
}

function renderAnswerWithMarkers(finalAnswer) {
  return finalAnswer.split(CITATION_MARKER_PATTERN).map((segment, index) => {
    if (!segment) {
      return null;
    }

    if (isCitationMarkerSegment(segment)) {
      return (
        <sup
          key={`${segment}-${index}`}
          className="citation-marker-inline"
          aria-label={`Citation marker ${segment}`}
        >
          {segment}
        </sup>
      );
    }

    return <Fragment key={`${segment}-${index}`}>{segment}</Fragment>;
  });
}

function normalizeOptionalText(value) {
  if (typeof value !== "string") {
    return null;
  }

  const normalized = value.trim();
  return normalized || null;
}

function citationHasSourceMetadata(citation) {
  return Boolean(
    normalizeOptionalText(citation.source_url) || normalizeOptionalText(citation.attribution)
  );
}

function normalizeErrorMessage(error) {
  if (error instanceof Error) {
    const normalized = error.message.trim();
    if (normalized) {
      return normalized;
    }
  }

  return "The backend request failed.";
}

async function requestJson(url, init = {}, timeoutMs = READINESS_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await window.fetch(url, {
      ...init,
      headers: {
        accept: "application/json",
        ...(init.headers ?? {}),
      },
      signal: controller.signal,
    });

    const responseText = await response.text();
    const payload = responseText ? JSON.parse(responseText) : null;

    if (!response.ok) {
      throw new Error(
        payload?.error?.message ?? `Request failed with status ${response.status}.`
      );
    }

    if (payload === null) {
      throw new Error("The backend returned an empty response.");
    }

    return payload;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("The backend request timed out.");
    }

    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

async function requestQuery(apiBaseUrl, question) {
  return requestJson(
    buildApiUrl(apiBaseUrl, "/query"),
    {
      method: "POST",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({ question }),
    },
    QUERY_TIMEOUT_MS
  );
}

async function requestReadiness(apiBaseUrl) {
  return requestJson(buildApiUrl(apiBaseUrl, "/readyz"));
}

function buildBackendStatus(nextStatus) {
  if (
    nextStatus.status === "ready" &&
    nextStatus.query_contract === "QueryResponse"
  ) {
    return {
      state: "ready",
      service: nextStatus.service,
      environment: nextStatus.environment,
      version: nextStatus.version,
      queryContract: nextStatus.query_contract,
      message: "Backend readiness probe passed.",
    };
  }

  return {
    state: "incompatible",
    service: nextStatus.service ?? null,
    environment: nextStatus.environment ?? null,
    version: nextStatus.version ?? null,
    queryContract: nextStatus.query_contract ?? null,
    message:
      "The backend responded, but its readiness metadata does not match the current browser contract.",
  };
}

function CitationMarkers({ citations }) {
  const hasSourceMetadata = citations.some(citationHasSourceMetadata);

  return (
    <div className="result-subsection">
      <h4>Citation markers</h4>
      <p className="helper-text result-note">
        This AWS MVP demo follows the frozen browser contract: citation markers only.
        Rich evidence cards are deferred because the current <code>/query</code>
        response does not include request-scoped evidence text.
        {hasSourceMetadata
          ? " Any source URL or attribution already exposed to the UI is shown directly under the matching marker."
          : " Source URL and attribution are not exposed to the browser in the current response shape."}
      </p>
      <ul className="marker-list">
        {citations.map((citation) => {
          const sourceUrl = normalizeOptionalText(citation.source_url);
          const attribution = normalizeOptionalText(citation.attribution);

          return (
            <li key={`${citation.marker}-${citation.chunk_id}`} className="marker-list-item">
              <code>{citation.marker}</code>
              {sourceUrl || attribution ? (
                <div className="citation-source-meta">
                  {sourceUrl ? (
                    <a href={sourceUrl} target="_blank" rel="noreferrer">
                      {sourceUrl}
                    </a>
                  ) : null}
                  {attribution ? <span>{attribution}</span> : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ResultPanel({ uiState, result, backendErrorMessage }) {
  if (uiState === "loading") {
    return (
      <div className="result-state result-state--loading" aria-live="polite">
        <p>Loading answer from the live backend…</p>
        <div className="loading-bar" aria-hidden="true" />
      </div>
    );
  }

  if (uiState === "empty_input") {
    return (
      <div className="result-state" aria-live="polite">
        <p>Enter a question to query the deployed backend.</p>
      </div>
    );
  }

  if (uiState === "backend_unavailable") {
    return (
      <div className="result-state result-state--error" aria-live="polite">
        <p>The backend is unavailable or incompatible right now.</p>
        <p>Retry after the API is healthy again.</p>
        {backendErrorMessage ? (
          <p className="result-detail">Last error: {backendErrorMessage}</p>
        ) : null}
      </div>
    );
  }

  if (!result) {
    return null;
  }

  if (result.refusal.is_refusal) {
    return (
      <div className="result-state result-state--refusal" aria-live="polite">
        <p className="result-kicker">Trust outcome</p>
        <h3>Refusal</h3>
        <p>{result.final_answer}</p>
        <dl className="result-metadata">
          <div>
            <dt>Reason code</dt>
            <dd>
              <code>{result.refusal.reason_code}</code>
            </dd>
          </div>
          <div>
            <dt>Evidence behavior</dt>
            <dd>Refusals do not carry citations in the current QueryResponse contract.</dd>
          </div>
        </dl>
      </div>
    );
  }

  return (
    <div className="result-state result-state--answer" aria-live="polite">
      <p className="result-kicker">Trust outcome</p>
      <h3>Supported answer</h3>
      <p className="answer-text">{renderAnswerWithMarkers(result.final_answer)}</p>
      {result.citations.length ? <CitationMarkers citations={result.citations} /> : null}
    </div>
  );
}

export default function App() {
  const apiBaseUrl = useMemo(() => readApiBaseUrl(), []);
  const [question, setQuestion] = useState("");
  const [uiState, setUiState] = useState("empty_input");
  const [result, setResult] = useState(null);
  const [backendErrorMessage, setBackendErrorMessage] = useState(null);
  const [statusText, setStatusText] = useState(
    "Enter a question to query the live AWS backend. The status area also probes /readyz for deployment diagnostics."
  );
  const [lastSubmittedQuestion, setLastSubmittedQuestion] = useState("");
  const [backendStatus, setBackendStatus] = useState(INITIAL_BACKEND_STATUS);

  const isSubmitDisabled = uiState === "loading" || !question.trim();

  const probeBackendStatus = useCallback(async () => {
    setBackendStatus((currentStatus) => ({
      ...currentStatus,
      state: "checking",
      message: "Checking backend readiness via /readyz.",
    }));

    try {
      const nextStatus = await requestReadiness(apiBaseUrl);
      setBackendStatus(buildBackendStatus(nextStatus));
    } catch (error) {
      setBackendStatus({
        state: "unavailable",
        service: null,
        environment: null,
        version: null,
        queryContract: null,
        message: normalizeErrorMessage(error),
      });
    }
  }, [apiBaseUrl]);

  useEffect(() => {
    void probeBackendStatus();
  }, [probeBackendStatus]);

  function handleQuestionChange(event) {
    const nextQuestion = event.target.value;
    setQuestion(nextQuestion);

    if (!nextQuestion.trim() && uiState !== "loading") {
      setUiState("empty_input");
      setResult(null);
      setBackendErrorMessage(null);
      setStatusText("Enter a question before submitting.");
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();

    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      setUiState("empty_input");
      setResult(null);
      setBackendErrorMessage(null);
      setStatusText("Enter a question before submitting.");
      return;
    }

    setLastSubmittedQuestion(trimmedQuestion);
    setUiState("loading");
    setResult(null);
    setBackendErrorMessage(null);
    setStatusText("Submitting a live POST /query request to the backend.");

    try {
      const nextResult = await requestQuery(apiBaseUrl, trimmedQuestion);
      setResult(nextResult);
      setStatusText(
        nextResult.refusal.is_refusal
          ? "Received an explicit refusal from the live backend."
          : "Received a supported answer from the live backend with visible citation markers."
      );
      setUiState(nextResult.refusal.is_refusal ? "refusal" : "supported_answer");
      void probeBackendStatus();
    } catch (error) {
      const nextErrorMessage = normalizeErrorMessage(error);
      setUiState("backend_unavailable");
      setResult(null);
      setBackendErrorMessage(nextErrorMessage);
      setStatusText(`Backend unavailable: ${nextErrorMessage}`);
      setBackendStatus({
        state: "unavailable",
        service: null,
        environment: null,
        version: null,
        queryContract: null,
        message: nextErrorMessage,
      });
    }
  }

  return (
    <div className="app-shell">
      <header className="panel page-header">
        <p className="eyebrow">AWS MVP browser demo</p>
        <h1>SupportDoc RAG Chatbot</h1>
        <p>
          Thin React SPA for the frozen <code>/query</code> contract, now wired to the
          live AWS backend.
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
              onChange={handleQuestionChange}
            />
            <p className="helper-text">
              The browser trims whitespace before submit, blocks empty input locally,
              and disables submit while a request is in flight.
            </p>
            <p className="privacy-warning" role="note">
              Do not paste secrets, credentials, access tokens, or other sensitive data
              into this demo.
            </p>

            <div className="form-actions">
              <button type="submit" disabled={isSubmitDisabled}>
                {uiState === "loading" ? "Loading…" : "Submit"}
              </button>
            </div>
          </form>
        </section>

        <section className="panel">
          <h2>Result panel</h2>
          <ResultPanel
            uiState={uiState}
            result={result}
            backendErrorMessage={backendErrorMessage}
          />
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
            <span className="status-label">Backend status</span>
            <span className={`status-pill status-pill--${backendStatus.state}`}>
              {BACKEND_STATUS_LABELS[backendStatus.state]}
            </span>
          </div>
          <div>
            <span className="status-label">Evidence display</span>
            <span>Citation markers only</span>
          </div>
          <div>
            <span className="status-label">query_contract</span>
            <code>{backendStatus.queryContract ?? "Unknown"}</code>
          </div>
          <div>
            <span className="status-label">Service</span>
            <span>{backendStatus.service ?? "Unknown"}</span>
          </div>
          <div>
            <span className="status-label">Environment</span>
            <span>{backendStatus.environment ?? "Unknown"}</span>
          </div>
          <div>
            <span className="status-label">Version</span>
            <span>{backendStatus.version ?? "Unknown"}</span>
          </div>
          <div>
            <span className="status-label">Last submitted question</span>
            <span>{lastSubmittedQuestion || "None yet"}</span>
          </div>
        </div>

        <div className="form-actions">
          <button
            type="button"
            className="secondary-button"
            disabled={backendStatus.state === "checking" || uiState === "loading"}
            onClick={() => {
              void probeBackendStatus();
            }}
          >
            {backendStatus.state === "checking"
              ? "Checking backend…"
              : "Refresh backend status"}
          </button>
        </div>

        <p className="status-message">{statusText}</p>
        <p className="helper-text status-meta">{backendStatus.message}</p>
      </aside>
    </div>
  );
}
