import { useEffect, useRef, useState } from "react";

const defaultApiBase = import.meta.env.VITE_API_BASE_URL?.trim() || "http://127.0.0.1:8000/v1";

const starterMessages = [
  {
    id: "assistant-intro",
    role: "assistant",
    body: "Hi! I am your coding helper. Ask a question about your project, or tap 'Help' for assistance.",
    canFeedback: false,
  },
];

export function renderInlineMarkdown(text) {
  const parts = [];
  const pattern = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`)/g;
  let lastIndex = 0;
  let match;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];
    if (token.startsWith("**") || token.startsWith("__")) {
      parts.push(<strong key={`${match.index}-strong`}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      parts.push(<code key={`${match.index}-code`}>{token.slice(1, -1)}</code>);
    }

    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
}

export function renderMessageBody(text) {
  if (typeof text !== "string") {
    return text;
  }

  const lines = text.split("\n");
  const elements = [];
  let listItems = [];
  let listType = null;

  const flushList = (key) => {
    if (!listItems.length) {
      return;
    }

    const Tag = listType === "ol" ? "ol" : "ul";
    elements.push(
      <Tag key={key} className="message-list-block">
        {listItems}
      </Tag>,
    );
    listItems = [];
    listType = null;
  };

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    const unorderedMatch = trimmed.match(/^[-*]\s+(.*)$/);
    const orderedMatch = trimmed.match(/^\d+\.\s+(.*)$/);

    if (!trimmed) {
      flushList(`list-${index}`);
      return;
    }

    if (unorderedMatch) {
      if (listType && listType !== "ul") {
        flushList(`list-${index}`);
      }
      listType = "ul";
      listItems.push(<li key={`li-${index}`}>{renderInlineMarkdown(unorderedMatch[1])}</li>);
      return;
    }

    if (orderedMatch) {
      if (listType && listType !== "ol") {
        flushList(`list-${index}`);
      }
      listType = "ol";
      listItems.push(<li key={`li-${index}`}>{renderInlineMarkdown(orderedMatch[1])}</li>);
      return;
    }

    flushList(`list-${index}`);
    elements.push(
      <p key={`p-${index}`} className="message-body">
        {renderInlineMarkdown(line)}
      </p>,
    );
  });

  flushList("list-final");
  return elements;
}

const VIEW_STORAGE_KEY = "vex-agent:view";

// Student view is what a student sees in class; research view adds the
// telemetry behind each message (proactive trigger, model, session id).
function readStoredView() {
  try {
    return window.localStorage.getItem(VIEW_STORAGE_KEY) === "research" ? "research" : "student";
  } catch {
    return "student";
  }
}

function createPendingAssistantMessage() {
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    body: "",
    canFeedback: false,
    isLoading: true,
  };
}

function RobotIcon({ className }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className}>
      <rect x="4.5" y="7.5" width="15" height="11" rx="3.5" />
      <path d="M12 7.5V4.5" />
      <circle cx="12" cy="3.6" r="0.9" />
      <path d="M9.4 12.4v1.2M14.6 12.4v1.2" />
      <path d="M2.5 12v2.5M21.5 12v2.5" />
    </svg>
  );
}

function Icon({ name }) {
  const paths = {
    chevronDown: <path d="m6 9 6 6 6-6" />,
    send: <path d="M5 12h13m-5-6 6 6-6 6" />,
    help: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M9.6 9.4a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.7" />
        <path d="M12 17.2v.1" />
      </>
    ),
    thumbUp: (
      <path d="M7.5 10.5v9h-3v-9h3Zm0 0 3.6-6.4a1.6 1.6 0 0 1 3 .9l-.6 4h4.8a2 2 0 0 1 2 2.4l-1.2 6a2 2 0 0 1-2 1.6H7.5" />
    ),
    thumbDown: (
      <path d="M16.5 13.5v-9h3v9h-3Zm0 0-3.6 6.4a1.6 1.6 0 0 1-3-.9l.6-4H5.7a2 2 0 0 1-2-2.4l1.2-6a2 2 0 0 1 2-1.6h9.6" />
    ),
    alert: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7.5v5.5M12 16.4v.1" />
      </>
    ),
  };
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="icon">
      {paths[name]}
    </svg>
  );
}

export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

const PANEL_MIN_WIDTH = 360;
const PANEL_MIN_HEIGHT = 520;
const PANEL_CORNER_RESIZE_MARGIN = 18;

function getResizeHandle(clientX, clientY, rect) {
  const nearLeft = Math.abs(clientX - rect.x) <= PANEL_CORNER_RESIZE_MARGIN;
  const nearRight = Math.abs(clientX - (rect.x + rect.width)) <= PANEL_CORNER_RESIZE_MARGIN;
  const nearTop = Math.abs(clientY - rect.y) <= PANEL_CORNER_RESIZE_MARGIN;
  const nearBottom = Math.abs(clientY - (rect.y + rect.height)) <= PANEL_CORNER_RESIZE_MARGIN;

  if (nearRight && nearBottom) {
    return "se";
  }
  if (nearLeft && nearBottom) {
    return "sw";
  }
  if (nearLeft && nearTop) {
    return "nw";
  }
  if (nearRight && nearTop) {
    return "ne";
  }
  return null;
}

function getCursorForResizeHandle(handle) {
  if (handle === "ne" || handle === "sw") {
    return "nesw-resize";
  }
  if (handle === "nw" || handle === "se") {
    return "nwse-resize";
  }
  return "";
}

function getDefaultPanelRect() {
  const width = 460;
  const height = 680;
  return {
    x: Math.max(12, window.innerWidth - width - 24),
    y: 32,
    width,
    height,
  };
}

function App() {
  const [studentIdDraft, setStudentIdDraft] = useState("");
  const [sessionIdDraft, setSessionIdDraft] = useState("");
  const [studentId, setStudentId] = useState("");
  const [sessionId, setSessionId] = useState("Detecting latest session");
  const [startError, setStartError] = useState("");
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState(starterMessages);
  const [pendingAction, setPendingAction] = useState("");
  const [reviewDrafts, setReviewDrafts] = useState({});
  const [openReviews, setOpenReviews] = useState({});
  const [pendingFeedback, setPendingFeedback] = useState({});
  const [panelRect, setPanelRect] = useState(getDefaultPanelRect);
  const [isChatOpen, setIsChatOpen] = useState(true);
  const [isInteractingWithPanel, setIsInteractingWithPanel] = useState(false);
  const [hoveredResizeHandle, setHoveredResizeHandle] = useState(null);
  const [view, setView] = useState(readStoredView);
  const [seenMessageCount, setSeenMessageCount] = useState(0);
  const panelRef = useRef(null);
  const interactionRef = useRef(null);
  const messageListRef = useRef(null);
  const messagesEndRef = useRef(null);
  const apiBase = defaultApiBase;
  const isResearchView = view === "research";
  // The start card sizes to its content; only the chat itself is resizable.
  const canResize = Boolean(studentId);

  // Replies that land while the chat is collapsed, so the launcher can say so.
  const unseenReplies = isChatOpen
    ? 0
    : messages
        .slice(seenMessageCount)
        .filter((message) => message.role === "assistant" && !message.isLoading).length;

  useEffect(() => {
    try {
      window.localStorage.setItem(VIEW_STORAGE_KEY, view);
    } catch {}
  }, [view]);

  const collapseChat = () => {
    setSeenMessageCount(messages.length);
    setIsChatOpen(false);
  };

  // Proactive push lane: subscribe to the SSE stream and append messages the agent
  // pushes on its own (trigger-driven). The stream starts at the current head, so no
  // history is replayed; we still dedupe by id in case a connection restarts.
  useEffect(() => {
    if (!studentId) {
      return undefined;
    }
    const source = new EventSource(`${apiBase}/students/${encodeURIComponent(studentId)}/stream`);
    source.addEventListener("assistant_message", (event) => {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      const proactiveId = `proactive-${payload.message_id}`;
      setMessages((current) =>
        current.some((message) => message.id === proactiveId)
          ? current
          : [
              ...current,
              {
                id: proactiveId,
                role: "assistant",
                body: payload.message,
                proactive: true,
                canFeedback: false,
                trigger: payload.trigger_type,
                triggerWhy: payload.trigger_why,
              },
            ],
      );
    });
    return () => source.close();
  }, [studentId, apiBase]);

  // Trip the Turnstile gate at page load instead of waiting for the first real
  // chat call (which otherwise doesn't happen until the student types an id and
  // starts a session). Side-effect-free; the response is discarded either way.
  useEffect(() => {
    getJson("/ping").catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const endInteraction = () => {
      const pointerId = interactionRef.current?.pointerId;
      if (pointerId !== undefined) {
        try {
          panelRef.current?.releasePointerCapture(pointerId);
        } catch {}
      }
      interactionRef.current = null;
      setHoveredResizeHandle(null);
      setIsInteractingWithPanel(false);
    };

    const handlePointerMove = (event) => {
      const interaction = interactionRef.current;
      if (!interaction) {
        return;
      }

      if (interaction.type === "drag") {
        setPanelRect((current) => {
          const nextX = clamp(
            event.clientX - interaction.offsetX,
            12,
            window.innerWidth - current.width - 12,
          );
          const nextY = clamp(event.clientY - interaction.offsetY, 12, window.innerHeight - 120);
          return {
            ...current,
            x: nextX,
            y: nextY,
          };
        });
        return;
      }

      if (interaction.type === "resize") {
        const deltaX = event.clientX - interaction.startPointerX;
        const deltaY = event.clientY - interaction.startPointerY;
        const startRight = interaction.startRect.x + interaction.startRect.width;
        const startBottom = interaction.startRect.y + interaction.startRect.height;
        const maxWidthFromLeft = window.innerWidth - interaction.startRect.x - 12;
        const maxHeightFromTop = window.innerHeight - interaction.startRect.y - 12;
        const maxWidthFromRight = startRight - 12;
        const maxHeightFromBottom = startBottom - 12;

        let nextX = interaction.startRect.x;
        let nextY = interaction.startRect.y;
        let nextWidth = interaction.startRect.width;
        let nextHeight = interaction.startRect.height;

        if (interaction.handle === "se" || interaction.handle === "ne") {
          nextWidth = clamp(
            interaction.startRect.width + deltaX,
            PANEL_MIN_WIDTH,
            maxWidthFromLeft,
          );
        }
        if (interaction.handle === "sw" || interaction.handle === "nw") {
          nextWidth = clamp(
            interaction.startRect.width - deltaX,
            PANEL_MIN_WIDTH,
            maxWidthFromRight,
          );
          nextX = startRight - nextWidth;
        }
        if (interaction.handle === "se" || interaction.handle === "sw") {
          nextHeight = clamp(
            interaction.startRect.height + deltaY,
            PANEL_MIN_HEIGHT,
            maxHeightFromTop,
          );
        }
        if (interaction.handle === "ne" || interaction.handle === "nw") {
          nextHeight = clamp(
            interaction.startRect.height - deltaY,
            PANEL_MIN_HEIGHT,
            maxHeightFromBottom,
          );
          nextY = startBottom - nextHeight;
        }

        setPanelRect({
          x: nextX,
          y: nextY,
          width: nextWidth,
          height: nextHeight,
        });
      }
    };

    const handlePointerUp = () => {
      endInteraction();
    };

    const handleWindowBlur = () => {
      endInteraction();
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);
    window.addEventListener("blur", handleWindowBlur);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
      window.removeEventListener("blur", handleWindowBlur);
    };
  }, []);

  useEffect(() => {
    if (!studentId || !isChatOpen) {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ block: "end" });
      if (messageListRef.current) {
        messageListRef.current.scrollTop = messageListRef.current.scrollHeight;
      }
    });

    return () => window.cancelAnimationFrame(frameId);
  }, [messages, isChatOpen, studentId]);

  const startDrag = (event) => {
    if (event.target.closest("button, textarea, input")) {
      return;
    }
    setIsInteractingWithPanel(true);
    try {
      panelRef.current?.setPointerCapture(event.pointerId);
    } catch {}
    interactionRef.current = {
      type: "drag",
      pointerId: event.pointerId,
      offsetX: event.clientX - panelRect.x,
      offsetY: event.clientY - panelRect.y,
    };
  };

  const handlePanelPointerMove = (event) => {
    if (interactionRef.current || !canResize) {
      return;
    }
    setHoveredResizeHandle(getResizeHandle(event.clientX, event.clientY, panelRect));
  };

  const handlePanelPointerLeave = () => {
    if (interactionRef.current) {
      return;
    }
    setHoveredResizeHandle(null);
  };

  const handlePanelPointerDownCapture = (event) => {
    if (!canResize || event.target.closest("button, textarea, input")) {
      return;
    }

    const resizeHandle = getResizeHandle(event.clientX, event.clientY, panelRect);
    if (!resizeHandle) {
      return;
    }

    setHoveredResizeHandle(resizeHandle);
    setIsInteractingWithPanel(true);
    event.stopPropagation();
    event.preventDefault();
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {}
    interactionRef.current = {
      type: "resize",
      pointerId: event.pointerId,
      handle: resizeHandle,
      startPointerX: event.clientX,
      startPointerY: event.clientY,
      startRect: { ...panelRect },
    };
  };

  const appendMessage = (message) => {
    setMessages((current) => [...current, message]);
  };

  // The server's TurnstileGateMiddleware 403s any /v1/* call from a browser
  // that hasn't solved the widget yet. Surface that as a DOM event so
  // TurnstileGate.jsx (mounted once, above <App/>) can show the challenge.
  const checkTurnstileRequired = (response, data) => {
    if (response.status === 403 && data.error === "turnstile_required") {
      window.dispatchEvent(new CustomEvent("turnstile:required"));
    }
  };

  const postJson = async (path, payload) => {
    const response = await fetch(`${apiBase}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      checkTurnstileRequired(response, data);
      throw new Error(data.detail || `Request failed with status ${response.status}`);
    }

    return data;
  };

  const getJson = async (path) => {
    const response = await fetch(`${apiBase}${path}`);
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      checkTurnstileRequired(response, data);
      throw new Error(data.detail || `Request failed with status ${response.status}`);
    }

    return data;
  };

  const updateMessage = (messageId, updater) => {
    setMessages((current) =>
      current.map((message) => (message.id === messageId ? updater(message) : message)),
    );
  };

  const handleFeedback = async (responseId, thumb) => {
    setPendingFeedback((current) => ({ ...current, [responseId]: thumb }));

    try {
      const comment = (reviewDrafts[responseId] || "").trim();
      await postJson(`/students/${studentId}/responses/${responseId}/feedback`, {
        thumb,
        comment: comment || null,
      });
      updateMessage(responseId, (message) => ({
        ...message,
        feedbackStatus: "Thanks!",
        selectedThumb: thumb,
      }));
    } catch (error) {
      updateMessage(responseId, (message) => ({
        ...message,
        feedbackStatus: `Feedback failed: ${error.message}`,
      }));
    } finally {
      setPendingFeedback((current) => {
        const next = { ...current };
        delete next[responseId];
        return next;
      });
    }
  };

  const handleReviewSubmit = async (responseId) => {
    const selectedThumb = messages.find((message) => message.id === responseId)?.selectedThumb;

    if (!selectedThumb) {
      updateMessage(responseId, (message) => ({
        ...message,
        feedbackStatus: "Choose thumbs up or thumbs down first.",
      }));
      return;
    }

    setPendingFeedback((current) => ({ ...current, [responseId]: "review" }));

    try {
      const comment = (reviewDrafts[responseId] || "").trim();
      await postJson(`/students/${studentId}/responses/${responseId}/feedback`, {
        thumb: selectedThumb,
        comment: comment || null,
      });
      updateMessage(responseId, (message) => ({
        ...message,
        feedbackStatus: "Note sent.",
      }));
      setOpenReviews((current) => ({ ...current, [responseId]: false }));
    } catch (error) {
      updateMessage(responseId, (message) => ({
        ...message,
        feedbackStatus: `Note failed: ${error.message}`,
      }));
    } finally {
      setPendingFeedback((current) => {
        const next = { ...current };
        delete next[responseId];
        return next;
      });
    }
  };

  const handleStudentStart = async (event) => {
    event.preventDefault();
    const trimmedStudentId = studentIdDraft.trim();
    const trimmedSessionId = sessionIdDraft.trim();
    if (!trimmedStudentId) {
      return;
    }
    setStartError("");
    setPendingAction("session");

    try {
      let resolvedSessionId = trimmedSessionId;

      if (!resolvedSessionId) {
        const sessionRecord = await getJson(`/students/${trimmedStudentId}/session`);
        resolvedSessionId = sessionRecord.session_id;
      }

      setStudentId(trimmedStudentId);
      setSessionId(resolvedSessionId);
    } catch (error) {
      setStartError(error.message);
    } finally {
      setPendingAction("");
    }
  };

  const handleComposerKeyDown = (event) => {
    if (event.key !== "Enter" || event.shiftKey) {
      return;
    }

    event.preventDefault();

    if (pendingAction === "message" || !draft.trim()) {
      return;
    }

    event.currentTarget.form?.requestSubmit();
  };

  // Typed questions and the Help button share one round trip: log the
  // student's turn, then ask the agent for a grounded reply.
  const askAgent = async ({ shownText, message, studentMessage, action, fallbackBody }) => {
    const studentTurn = {
      id: crypto.randomUUID(),
      role: "student",
      body: shownText,
      status: "sending",
    };
    const pendingAssistantMessage = createPendingAssistantMessage();

    appendMessage(studentTurn);
    appendMessage(pendingAssistantMessage);
    setPendingAction(action);

    try {
      const messagePayload = {
        message,
        ...(sessionIdDraft.trim() ? { session_id: sessionIdDraft.trim() } : {}),
      };
      const messageResponse = await postJson(`/students/${studentId}/messages`, messagePayload);
      setSessionId(messageResponse.session_id);
      const responseRecord = await postJson(`/students/${studentId}/responses`, {
        message_id: messageResponse.message_id,
        session_id: messageResponse.session_id,
        student_message: studentMessage,
      });
      setSessionId(responseRecord.session_id);
      setMessages((current) =>
        current.map((entry) =>
          entry.id === studentTurn.id
            ? { ...entry, status: "sent" }
            : entry.id === pendingAssistantMessage.id
              ? {
                  id: responseRecord.response_id,
                  role: "assistant",
                  body: responseRecord.response_text,
                  model: responseRecord.llm_model || null,
                  canFeedback: true,
                }
              : entry,
        ),
      );
    } catch (error) {
      setMessages((current) =>
        current.map((entry) =>
          entry.id === studentTurn.id
            ? { ...entry, status: "error", error: error.message }
            : entry.id === pendingAssistantMessage.id
              ? {
                  ...entry,
                  body: fallbackBody,
                  error: error.message,
                  isLoading: false,
                }
              : entry,
        ),
      );
    } finally {
      setPendingAction("");
    }
  };

  const handleSend = (event) => {
    event.preventDefault();

    const trimmedDraft = draft.trim();
    if (!trimmedDraft) {
      return;
    }

    setDraft("");
    askAgent({
      shownText: trimmedDraft,
      message: trimmedDraft,
      studentMessage: trimmedDraft,
      action: "message",
      fallbackBody: "The agent ran into a delay. Try asking again in a moment.",
    });
  };

  const handleHelp = () => {
    askAgent({
      shownText: "Help",
      message: "",
      studentMessage: "Help",
      action: "help",
      fallbackBody: "Help could not be sent right now.",
    });
  };

  const isAgentBusy = pendingAction === "help" || pendingAction === "message";

  const renderStudentStatus = (message) => {
    if (message.status === "sending") {
      return <span className="msg-status">Sending…</span>;
    }
    if (message.status === "error") {
      return (
        <span className="msg-status msg-status-error">
          <Icon name="alert" />
          {`Not sent: ${message.error}`}
        </span>
      );
    }
    return null;
  };

  const renderResearchDetails = (message) => {
    if (!isResearchView) {
      return null;
    }
    const rows = [];
    if (message.proactive) {
      rows.push(["Trigger", <code key="t">{message.trigger || "unknown"}</code>]);
      if (message.triggerWhy) {
        rows.push(["Why", message.triggerWhy]);
      }
    }
    if (message.model) {
      rows.push(["Model", <code key="m">{message.model}</code>]);
    }
    if (message.error) {
      rows.push(["Error", message.error]);
    }
    if (!rows.length) {
      return null;
    }
    return (
      <dl className="research-details">
        {rows.map(([term, detail]) => (
          <div key={term}>
            <dt>{term}</dt>
            <dd>{detail}</dd>
          </div>
        ))}
      </dl>
    );
  };

  const renderFeedback = (message) => {
    const pending = pendingFeedback[message.id];
    const isNoteOpen = Boolean(openReviews[message.id]);
    return (
      <div className="feedback">
        <div className="feedback-row">
          {[
            ["up", "thumbUp", "This helped"],
            ["down", "thumbDown", "This didn't help"],
          ].map(([thumb, icon, label]) => (
            <button
              key={thumb}
              type="button"
              className="feedback-thumb"
              aria-pressed={message.selectedThumb === thumb}
              onClick={() => handleFeedback(message.id, thumb)}
              disabled={Boolean(pending)}
              aria-label={label}
              title={label}
            >
              {pending === thumb ? (
                <span className="spinner" aria-hidden="true" />
              ) : (
                <Icon name={icon} />
              )}
            </button>
          ))}
          <button
            type="button"
            className="feedback-note-toggle"
            aria-expanded={isNoteOpen}
            onClick={() =>
              setOpenReviews((current) => ({
                ...current,
                [message.id]: !current[message.id],
              }))
            }
          >
            {isNoteOpen ? "Hide note" : "Add a note"}
          </button>
          {message.feedbackStatus ? (
            <span className="feedback-status" role="status">
              {message.feedbackStatus}
            </span>
          ) : null}
        </div>
        {isNoteOpen ? (
          <div className="feedback-note">
            <label className="sr-only" htmlFor={`note-${message.id}`}>
              Note about this reply
            </label>
            <textarea
              id={`note-${message.id}`}
              rows="2"
              value={reviewDrafts[message.id] || ""}
              onChange={(event) =>
                setReviewDrafts((current) => ({
                  ...current,
                  [message.id]: event.target.value,
                }))
              }
              placeholder="What helped, or what was confusing?"
            />
            <button
              type="button"
              className="button-small"
              onClick={() => handleReviewSubmit(message.id)}
              disabled={Boolean(pending)}
            >
              {pending === "review" ? "Sending…" : "Send note"}
            </button>
          </div>
        ) : null}
      </div>
    );
  };

  return (
    <main className="overlay-shell">
      <iframe
        className={`background-frame ${isInteractingWithPanel ? "background-frame-inactive" : ""}`}
        src="https://research-vr.vex.com/"
        title="Research VR"
      />

      {isChatOpen ? (
        <section
          ref={panelRef}
          className={`chat-overlay ${!studentId ? "chat-overlay-start" : ""} ${
            isInteractingWithPanel ? "is-moving" : ""
          }`}
          aria-label="Guide Bot chat"
          onPointerDownCapture={handlePanelPointerDownCapture}
          onPointerMove={handlePanelPointerMove}
          onPointerLeave={handlePanelPointerLeave}
          style={{
            left: `${panelRect.x}px`,
            top: `${panelRect.y}px`,
            width: `${panelRect.width}px`,
            height: canResize ? `${panelRect.height}px` : undefined,
            cursor: getCursorForResizeHandle(hoveredResizeHandle),
          }}
        >
          <header className="panel-header" onPointerDown={startDrag}>
            <span className="panel-mark" aria-hidden="true">
              <RobotIcon className="robot-icon" />
            </span>
            <div className="panel-title">
              <h1>Guide Bot</h1>
              {studentId ? (
                <p>
                  <span>{studentId}</span>
                  <span className="panel-title-sep" aria-hidden="true" />
                  <span>GO-Mars</span>
                  {isResearchView ? (
                    <>
                      <span className="panel-title-sep" aria-hidden="true" />
                      <span className="panel-session" title={sessionId}>
                        {sessionId}
                      </span>
                    </>
                  ) : null}
                </p>
              ) : (
                <p>Your VEXcode VR coding helper</p>
              )}
            </div>
            <div className="panel-actions">
              {studentId ? (
                <button
                  type="button"
                  className="help-button"
                  onClick={handleHelp}
                  disabled={isAgentBusy}
                >
                  <Icon name="help" />
                  {pendingAction === "help" ? "Asking…" : "Help"}
                </button>
              ) : null}
              <button
                type="button"
                className="panel-icon-button"
                onClick={collapseChat}
                aria-label="Collapse chat"
                title="Collapse chat"
              >
                <Icon name="chevronDown" />
              </button>
            </div>
          </header>

          {!studentId ? (
            <div className="start">
              <h2>Start Chat</h2>
              <p>Enter your student ID to begin.</p>
              <form className="start-form" onSubmit={handleStudentStart}>
                <label htmlFor="student-id">Student ID</label>
                <input
                  id="student-id"
                  type="text"
                  value={studentIdDraft}
                  onChange={(event) => setStudentIdDraft(event.target.value)}
                  placeholder="e.g. mars-042"
                  autoComplete="off"
                  spellCheck="false"
                  disabled={pendingAction === "session"}
                  aria-invalid={Boolean(startError)}
                  aria-describedby={startError ? "start-error" : undefined}
                />
                <button
                  type="submit"
                  className="button-primary"
                  disabled={pendingAction === "session" || !studentIdDraft.trim()}
                >
                  {pendingAction === "session" ? "Finding your session…" : "Start Chat"}
                </button>
              </form>
              {startError ? (
                <p className="start-error" id="start-error" role="alert">
                  <Icon name="alert" />
                  {startError}
                </p>
              ) : null}
            </div>
          ) : (
            <>
              <section className="message-list" aria-label="Conversation" ref={messageListRef}>
                {messages.map((message) =>
                  message.role === "student" ? (
                    <article key={message.id} className="msg msg-student">
                      <span className="sr-only">You said: </span>
                      <div className="bubble">{renderMessageBody(message.body)}</div>
                      {renderStudentStatus(message)}
                    </article>
                  ) : (
                    <article
                      key={message.id}
                      className={`msg msg-agent ${message.proactive ? "msg-checkin" : ""}`}
                    >
                      <span className="msg-avatar" aria-hidden="true">
                        <RobotIcon className="robot-icon" />
                      </span>
                      <div className="msg-main">
                        <div className="msg-author">
                          Guide Bot
                          {message.proactive ? (
                            <span className="checkin-tag">
                              {isResearchView ? "Proactive check-in" : "Checking in"}
                            </span>
                          ) : null}
                        </div>
                        <div className={`bubble ${message.error ? "bubble-error" : ""}`}>
                          {message.isLoading ? (
                            <span className="thinking" role="status">
                              <span className="sr-only">Guide Bot is thinking</span>
                              <span aria-hidden="true" />
                              <span aria-hidden="true" />
                              <span aria-hidden="true" />
                            </span>
                          ) : (
                            renderMessageBody(message.body)
                          )}
                          {renderResearchDetails(message)}
                        </div>
                        {message.canFeedback ? renderFeedback(message) : null}
                      </div>
                    </article>
                  ),
                )}
                <div ref={messagesEndRef} aria-hidden="true" />
              </section>

              <form className="composer" onSubmit={handleSend}>
                <div className="composer-field">
                  <label className="sr-only" htmlFor="student-message">
                    Message
                  </label>
                  <textarea
                    id="student-message"
                    rows="2"
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={handleComposerKeyDown}
                    placeholder="Ask about your program, your bug, or what to try next."
                  />
                  <button
                    type="submit"
                    className="send-button"
                    disabled={pendingAction === "message" || !draft.trim()}
                  >
                    {pendingAction === "message" ? "Sending…" : "Send"}
                    <Icon name="send" />
                  </button>
                </div>
                <div className="composer-foot">
                  <div className="view-toggle" role="group" aria-label="View">
                    {[
                      ["student", "Student"],
                      ["research", "Research"],
                    ].map(([value, label]) => (
                      <button
                        key={value}
                        type="button"
                        aria-pressed={view === value}
                        onClick={() => setView(value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <span className="composer-hint">
                    <kbd>Enter</kbd> to send, <kbd>Shift</kbd> + <kbd>Enter</kbd> for a new line
                  </span>
                </div>
              </form>
              <span className="resize-grip" aria-hidden="true" />
            </>
          )}
        </section>
      ) : (
        <button type="button" className="chat-launcher" onClick={() => setIsChatOpen(true)}>
          <span className="panel-mark" aria-hidden="true">
            <RobotIcon className="robot-icon" />
          </span>
          Open Chat
          {unseenReplies ? (
            <span className="launcher-badge">
              {unseenReplies} new
              <span className="sr-only"> {unseenReplies === 1 ? "reply" : "replies"}</span>
            </span>
          ) : null}
        </button>
      )}
    </main>
  );
}

export default App;
