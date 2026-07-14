import { useEffect, useRef, useState } from "react";

const defaultApiBase =
  import.meta.env.VITE_API_BASE_URL?.trim() || "http://127.0.0.1:8000/v1";

const starterMessages = [
  {
    id: "assistant-intro",
    role: "assistant",
    body:
      "Hi! I am your coding helper. Ask a question about your project, or tap 'Help' for assistance.",
    meta: "Ready to help",
    canFeedback: false,
  },
];

function renderInlineMarkdown(text) {
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

function renderMessageBody(text) {
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
    elements.push(<Tag key={key} className="message-list-block">{listItems}</Tag>);
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
      listItems.push(
        <li key={`li-${index}`}>{renderInlineMarkdown(unorderedMatch[1])}</li>,
      );
      return;
    }

    if (orderedMatch) {
      if (listType && listType !== "ol") {
        flushList(`list-${index}`);
      }
      listType = "ol";
      listItems.push(
        <li key={`li-${index}`}>{renderInlineMarkdown(orderedMatch[1])}</li>,
      );
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

function createPendingAssistantMessage() {
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    body: "",
    meta: "Thinking...",
    canFeedback: false,
    isLoading: true,
  };
}

function MessageAvatar({ role }) {
  if (role === "student") {
    return (
      <div className="message-avatar message-avatar-student" aria-hidden="true">
        <svg viewBox="0 0 48 48" className="message-avatar-svg">
          <circle cx="24" cy="18" r="9" />
          <path d="M10 40c2.8-7.4 9.1-11 14-11s11.2 3.6 14 11" />
        </svg>
      </div>
    );
  }

  return (
    <div className="message-avatar message-avatar-agent" aria-hidden="true">
      <svg viewBox="0 0 48 48" className="message-avatar-svg">
        <rect x="11" y="14" width="26" height="20" rx="6" />
        <circle cx="19" cy="24" r="2.8" />
        <circle cx="29" cy="24" r="2.8" />
        <path d="M18 31h12" />
        <path d="M24 8v6" />
        <path d="M14 38v4" />
        <path d="M34 38v4" />
      </svg>
    </div>
  );
}

function clamp(value, min, max) {
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
  const panelRef = useRef(null);
  const interactionRef = useRef(null);
  const messageListRef = useRef(null);
  const messagesEndRef = useRef(null);
  const apiBase = defaultApiBase;

  // Proactive push lane: subscribe to the SSE stream and append messages the agent
  // pushes on its own (trigger-driven). The stream starts at the current head, so no
  // history is replayed; we still dedupe by id in case a connection restarts.
  useEffect(() => {
    if (!studentId) {
      return undefined;
    }
    const source = new EventSource(
      `${apiBase}/students/${encodeURIComponent(studentId)}/stream`,
    );
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
                meta: "Proactive check-in",
                canFeedback: false,
              },
            ],
      );
    });
    return () => source.close();
  }, [studentId, apiBase]);

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
          const nextY = clamp(
            event.clientY - interaction.offsetY,
            12,
            window.innerHeight - 120,
          );
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
    if (interactionRef.current) {
      return;
    }
    setHoveredResizeHandle(
      getResizeHandle(event.clientX, event.clientY, panelRect),
    );
  };

  const handlePanelPointerLeave = () => {
    if (interactionRef.current) {
      return;
    }
    setHoveredResizeHandle(null);
  };

  const handlePanelPointerDownCapture = (event) => {
    if (event.target.closest("button, textarea, input")) {
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
      throw new Error(data.detail || `Request failed with status ${response.status}`);
    }

    return data;
  };

  const getJson = async (path) => {
    const response = await fetch(`${apiBase}${path}`);
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.detail || `Request failed with status ${response.status}`);
    }

    return data;
  };

  const updateMessage = (messageId, updater) => {
    setMessages((current) =>
      current.map((message) =>
        message.id === messageId ? updater(message) : message,
      ),
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
        feedbackStatus: thumb === "up" ? "Thanks for the thumbs up." : "Thanks for the feedback.",
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
        feedbackStatus: "Review sent.",
      }));
      setOpenReviews((current) => ({ ...current, [responseId]: false }));
    } catch (error) {
      updateMessage(responseId, (message) => ({
        ...message,
        feedbackStatus: `Review failed: ${error.message}`,
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

  const handleSend = async (event) => {
    event.preventDefault();

    const trimmedDraft = draft.trim();
    if (!trimmedDraft) {
      return;
    }

    const optimisticMessage = {
      id: crypto.randomUUID(),
      role: "student",
      body: trimmedDraft,
      meta: "Sending",
    };
    const pendingAssistantMessage = createPendingAssistantMessage();

    appendMessage(optimisticMessage);
    appendMessage(pendingAssistantMessage);
    setDraft("");
    setPendingAction("message");

    try {
      const messagePayload = {
        message: trimmedDraft,
        ...(sessionIdDraft.trim() ? { session_id: sessionIdDraft.trim() } : {}),
      };
      const messageResponse = await postJson(`/students/${studentId}/messages`, messagePayload);
      setSessionId(messageResponse.session_id);
      const responseRecord = await postJson(`/students/${studentId}/responses`, {
        message_id: messageResponse.message_id,
        session_id: messageResponse.session_id,
        student_message: trimmedDraft,
      });
      setSessionId(responseRecord.session_id);
      setMessages((current) =>
        [
          ...current.map((message) =>
            message.id === optimisticMessage.id
              ? {
                  ...message,
                  meta: "Sent",
                }
              : message.id === pendingAssistantMessage.id
                ? {
                    id: responseRecord.response_id,
                    role: "assistant",
                    body: responseRecord.response_text,
                    meta: responseRecord.llm_model || "Generated response",
                    canFeedback: true,
                    isLoading: false,
                  }
                : message,
          ),
        ],
      );
    } catch (error) {
      setMessages((current) =>
        current.map((message) =>
          message.id === optimisticMessage.id
            ? {
                ...message,
                meta: `Failed to send: ${error.message}`,
              }
            : message.id === pendingAssistantMessage.id
              ? {
                  ...message,
                  body: "The agent ran into a delay. Try asking again in a moment.",
                  meta: `Failed: ${error.message}`,
                  isLoading: false,
                }
            : message,
        ),
      );
    } finally {
      setPendingAction("");
    }
  };

  const handleHelp = async () => {
    const helpMessage = {
      id: crypto.randomUUID(),
      role: "student",
      body: "Help",
      meta: "Sending",
    };
    const pendingAssistantMessage = createPendingAssistantMessage();

    appendMessage(helpMessage);
    appendMessage(pendingAssistantMessage);
    setPendingAction("help");

    try {
      const messagePayload = {
        message: "",
        ...(sessionIdDraft.trim() ? { session_id: sessionIdDraft.trim() } : {}),
      };
      const messageResponse = await postJson(`/students/${studentId}/messages`, messagePayload);
      setSessionId(messageResponse.session_id);
      const responseRecord = await postJson(`/students/${studentId}/responses`, {
        message_id: messageResponse.message_id,
        session_id: messageResponse.session_id,
        student_message: "Help",
      });
      setSessionId(responseRecord.session_id);
      setMessages((current) =>
        [
          ...current.map((message) =>
            message.id === helpMessage.id
              ? {
                  ...message,
                  meta: "Sent",
                }
              : message.id === pendingAssistantMessage.id
                ? {
                    id: responseRecord.response_id,
                    role: "assistant",
                    body: responseRecord.response_text,
                    meta: responseRecord.llm_model || "Generated response",
                    canFeedback: true,
                    isLoading: false,
                  }
                : message,
          ),
        ],
      );
    } catch (error) {
      setMessages((current) =>
        current.map((message) =>
          message.id === helpMessage.id
            ? {
                ...message,
                meta: `Failed to send: ${error.message}`,
              }
            : message.id === pendingAssistantMessage.id
              ? {
                  ...message,
                  body: "Help could not be sent right now.",
                  meta: `Failed to send: ${error.message}`,
                  isLoading: false,
                }
              : message,
        ),
      );
    } finally {
      setPendingAction("");
    }
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
          className={`chat-overlay ${!studentId ? "chat-overlay-start" : ""}`}
          onPointerDownCapture={handlePanelPointerDownCapture}
          onPointerMove={handlePanelPointerMove}
          onPointerLeave={handlePanelPointerLeave}
          style={{
            left: `${panelRect.x}px`,
            top: `${panelRect.y}px`,
            width: `${panelRect.width}px`,
            height: `${panelRect.height}px`,
            cursor: getCursorForResizeHandle(hoveredResizeHandle),
          }}
        >
          {studentId ? (
            <header className="toolbar draggable-toolbar" onPointerDown={startDrag}>
              <div className="toolbar-copy">
                <h1>Chat</h1>
                <p>{`${studentId} · GO-Mars · ${sessionId}`}</p>
              </div>
              <div className="toolbar-actions">
                <button
                  type="button"
                  className="help-button"
                  onClick={handleHelp}
                  disabled={pendingAction === "help" || pendingAction === "message"}
                >
                  {pendingAction === "help" ? "Sending..." : "Help"}
                </button>
                <button
                  type="button"
                  className="chat-close-button"
                  onClick={() => setIsChatOpen(false)}
                  aria-label="Collapse chat"
                  title="Collapse chat"
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true" className="chat-close-icon">
                    <path d="M6 9l6 6 6-6" />
                  </svg>
                  <span className="chat-close-text">Collapse</span>
                </button>
              </div>
            </header>
          ) : null}
          {!studentId ? (
            <button
              type="button"
              className="chat-close-button chat-close-button-floating"
              onClick={() => setIsChatOpen(false)}
              aria-label="Collapse chat"
              title="Collapse chat"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true" className="chat-close-icon">
                <path d="M6 9l6 6 6-6" />
              </svg>
              <span className="chat-close-text">Collapse</span>
            </button>
          ) : null}

        <div className="workspace workspace-overlay">
          {!studentId ? (
            <div className="start-drag-surface" onPointerDown={startDrag}>
              <section
                className="start-card start-card-inline"
                onPointerDown={(event) => event.stopPropagation()}
              >
                <h2>Start Chat</h2>
                <p>Enter your student ID. Session ID is optional if you want to target a specific test session.</p>
                <form className="start-form" onSubmit={handleStudentStart}>
                  <label className="sr-only" htmlFor="student-id">
                    Student ID
                  </label>
                  <input
                    id="student-id"
                    type="text"
                    value={studentIdDraft}
                    onChange={(event) => setStudentIdDraft(event.target.value)}
                    placeholder="Student ID"
                    autoComplete="off"
                    disabled={pendingAction === "session"}
                  />
                  <label className="sr-only" htmlFor="session-id">
                    Session ID
                  </label>
                  <input
                    id="session-id"
                    type="text"
                    value={sessionIdDraft}
                    onChange={(event) => setSessionIdDraft(event.target.value)}
                    placeholder="Session ID (optional)"
                    autoComplete="off"
                    disabled={pendingAction === "session"}
                  />
                  <button type="submit" disabled={pendingAction === "session"}>
                    {pendingAction === "session" ? "Loading..." : "Start Chat"}
                  </button>
                </form>
                {startError ? <p className="start-error">{startError}</p> : null}
              </section>
            </div>
          ) : (
            <section className="message-list" aria-label="Conversation" ref={messageListRef}>
              {messages.map((message) => (
                <article
                  key={message.id}
                  className={`message-row ${message.role === "student" ? "outgoing" : "incoming"}`}
                >
                  <MessageAvatar role={message.role} />
                  <div className="message-card">
                    <div className="message-bubble">
                      <div className="message-label">
                        {message.role === "student" ? "You" : "Guide Bot"}
                      </div>
                      <div className="message-body-wrap">
                        {message.isLoading ? (
                          <div className="thinking-indicator" aria-label="Agent is thinking">
                            <span className="thinking-text">Guide Bot is thinking</span>
                            <span className="thinking-dots" aria-hidden="true">
                              <span />
                              <span />
                              <span />
                            </span>
                          </div>
                        ) : (
                          renderMessageBody(message.body)
                        )}
                      </div>
                      <span className="message-meta">{message.meta}</span>
                      {message.role === "assistant" && message.canFeedback ? (
                        <div className="feedback-panel">
                          <div className="feedback-actions">
                            <button
                              type="button"
                              className={`icon-button ${message.selectedThumb === "up" ? "selected" : ""}`}
                              onClick={() => handleFeedback(message.id, "up")}
                              disabled={Boolean(pendingFeedback[message.id])}
                              aria-label="Thumbs up"
                              title="Thumbs up"
                            >
                              {pendingFeedback[message.id] === "up" ? (
                                "..."
                              ) : (
                                <svg viewBox="0 0 24 24" aria-hidden="true">
                                  <path d="M10 21H6a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h4v11Zm2-11 2.6-6.1A1.5 1.5 0 0 1 16 3a2 2 0 0 1 2 2v4h2.7a2 2 0 0 1 2 2.4l-1.2 6A2 2 0 0 1 19.5 19H12V10Z" />
                                </svg>
                              )}
                            </button>
                            <button
                              type="button"
                              className={`icon-button ${message.selectedThumb === "down" ? "selected" : ""}`}
                              onClick={() => handleFeedback(message.id, "down")}
                              disabled={Boolean(pendingFeedback[message.id])}
                              aria-label="Thumbs down"
                              title="Thumbs down"
                            >
                              {pendingFeedback[message.id] === "down" ? (
                                "..."
                              ) : (
                                <svg viewBox="0 0 24 24" aria-hidden="true">
                                  <path d="M14 3h4a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-4V3Zm-2 11-2.6 6.1A1.5 1.5 0 0 1 8 21a2 2 0 0 1-2-2v-4H3.3a2 2 0 0 1-2-2.4l1.2-6A2 2 0 0 1 4.5 5H12v9Z" />
                                </svg>
                              )}
                            </button>
                            <button
                              type="button"
                              className="review-toggle"
                              onClick={() =>
                                setOpenReviews((current) => ({
                                  ...current,
                                  [message.id]: !current[message.id],
                                }))
                              }
                            >
                              {openReviews[message.id] ? "Hide Review" : "Add Review"}
                            </button>
                          </div>
                          {openReviews[message.id] ? (
                            <div className="review-form">
                              <textarea
                                rows="2"
                                value={reviewDrafts[message.id] || ""}
                                onChange={(event) =>
                                  setReviewDrafts((current) => ({
                                    ...current,
                                    [message.id]: event.target.value,
                                  }))
                                }
                                placeholder="Write a review if you want."
                              />
                              <button
                                type="button"
                                className="send-review"
                                onClick={() => handleReviewSubmit(message.id)}
                                disabled={Boolean(pendingFeedback[message.id])}
                              >
                                {pendingFeedback[message.id] === "review" ? "Sending..." : "Send Review"}
                              </button>
                            </div>
                          ) : null}
                          {message.feedbackStatus ? (
                            <div className="feedback-status">{message.feedbackStatus}</div>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  </div>
                </article>
              ))}
              <div ref={messagesEndRef} aria-hidden="true" />
            </section>
          )}
        </div>

        {studentId ? (
          <form className="composer" onSubmit={handleSend}>
            <label className="sr-only" htmlFor="student-message">
              Message
            </label>
            <textarea
              id="student-message"
              rows="3"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder="Ask about your program, your bug, or what to try next."
            />
            <div className="composer-footer">
              <button type="submit" disabled={pendingAction === "message" || !draft.trim()}>
                {pendingAction === "message" ? "Sending..." : "Send"}
              </button>
            </div>
          </form>
        ) : null}
        </section>
      ) : null}

      {!isChatOpen ? (
        <button
          type="button"
          className="chat-launcher"
          onClick={() => setIsChatOpen(true)}
        >
          Open Chat
        </button>
      ) : null}
    </main>
  );
}

export default App;
