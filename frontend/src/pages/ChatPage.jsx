import { useState, useEffect, useRef, useCallback } from "react";
import { askQuestion, listSessions, getSession, deleteSession } from "../api";

export default function ChatPage() {
  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputQuestion, setInputQuestion] = useState("");
  const [isAsking, setIsAsking] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState(null);
  const [copiedIndex, setCopiedIndex] = useState(null);
  const [error, setError] = useState("");

  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  const fetchSessions = useCallback(async () => {
    try {
      const data = await listSessions();
      setSessions(data || []);
    } catch (err) {
      console.error("Failed to load sessions:", err);
    }
  }, []);

  // Load user sessions list on mount
  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // Scroll to bottom whenever messages update
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isAsking]);

  const handleSelectSession = async (sessionId) => {
    if (sessionId === currentSessionId) return;
    setCurrentSessionId(sessionId);
    setLoadingHistory(true);
    setError("");
    setSelectedCitation(null);
    try {
      const detail = await getSession(sessionId);
      setMessages(detail.messages || []);
    } catch (err) {
      setError("Failed to load conversation history: " + err.message);
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleNewChat = () => {
    setCurrentSessionId(null);
    setMessages([]);
    setError("");
    setSelectedCitation(null);
    if (textareaRef.current) textareaRef.current.focus();
  };

  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this chat session?")) return;
    try {
      await deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (currentSessionId === sessionId) {
        handleNewChat();
      }
    } catch (err) {
      setError("Failed to delete session: " + err.message);
    }
  };

  const handleSubmit = async (e) => {
    e?.preventDefault();
    const q = inputQuestion.trim();
    if (!q || isAsking) return;

    setInputQuestion("");
    setError("");

    // Optimistically append user message
    const optimisticUserMsg = {
      id: "temp-" + Date.now(),
      role: "user",
      content: q,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUserMsg]);
    setIsAsking(true);

    try {
      const res = await askQuestion(q, currentSessionId);
      // If this was a new session, update session id and reload session list
      if (!currentSessionId && res.session_id) {
        setCurrentSessionId(res.session_id);
        fetchSessions();
      }

      // Append assistant answer
      const assistantMsg = {
        id: "resp-" + Date.now(),
        role: "assistant",
        content: res.answer,
        citations: res.citations || [],
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setError(err.message || "Failed to process question. Please try again.");
    } finally {
      setIsAsking(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const copyToClipboard = (text, idx) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(idx);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const promptSuggestions = [
    "What are the main institutional guidelines?",
    "Summarize the key compliance requirements and rules.",
    "What is the standard procedure outlined in the documents?",
  ];

  return (
    <div className="chat-layout">
      {/* Sidebar: Conversation Sessions */}
      <aside className="chat-sidebar">
        <div className="sidebar-top">
          <button className="btn-new-chat" onClick={handleNewChat}>
            <span className="btn-plus">+</span> New Conversation
          </button>
        </div>

        <div className="sessions-list">
          <div className="sessions-header">Recent Conversations</div>
          {sessions.length === 0 ? (
            <div className="sessions-empty">No conversation history yet.</div>
          ) : (
            sessions.map((s) => (
              <div
                key={s.id}
                className={`session-item ${currentSessionId === s.id ? "active" : ""}`}
                onClick={() => handleSelectSession(s.id)}
              >
                <span className="session-icon">💬</span>
                <span className="session-title" title={s.title}>
                  {s.title || "Untitled Session"}
                </span>
                <button
                  className="btn-session-delete"
                  title="Delete conversation"
                  onClick={(e) => handleDeleteSession(e, s.id)}
                >
                  ✕
                </button>
              </div>
            ))
          )}
        </div>
      </aside>

      {/* Main Conversation Stream */}
      <main className="chat-main">
        {error && <div className="alert alert-error chat-alert">{error}</div>}

        <div className="messages-stream">
          {loadingHistory ? (
            <div className="loading-state">
              <div className="spinner"></div>
              <p>Retrieving session history...</p>
            </div>
          ) : messages.length === 0 ? (
            <div className="chat-welcome">
              <div className="welcome-badge">AI Knowledge Engine</div>
              <h2 className="welcome-title">How can I assist you today?</h2>
              <p className="welcome-desc">
                Ask questions regarding your institution’s policies, handbooks, regulations, or documentation.
                Every response is synthesized with exact document and page citations.
              </p>

              <div className="suggestions-grid">
                {promptSuggestions.map((sug, i) => (
                  <button
                    key={i}
                    className="suggestion-card"
                    onClick={() => {
                      setInputQuestion(sug);
                      if (textareaRef.current) textareaRef.current.focus();
                    }}
                  >
                    <span className="suggestion-icon">💡</span>
                    <span>{sug}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((m, idx) => (
              <div
                key={m.id || idx}
                className={`message-row ${m.role === "user" ? "message-user" : "message-assistant"}`}
              >
                <div className="message-avatar">
                  {m.role === "user" ? "👤" : "◈"}
                </div>
                <div className="message-content-wrapper">
                  <div className="message-bubble">
                    <div className="message-header">
                      <span className="message-sender">
                        {m.role === "user" ? "You" : "DocQA Assistant"}
                      </span>
                      {m.role === "assistant" && (
                        <button
                          className="btn-copy"
                          onClick={() => copyToClipboard(m.content, idx)}
                          title="Copy answer"
                        >
                          {copiedIndex === idx ? "✓ Copied" : "Copy"}
                        </button>
                      )}
                    </div>
                    <div className="message-text">{m.content}</div>
                  </div>

                  {/* Grounded Citations Box */}
                  {m.role === "assistant" && m.citations && m.citations.length > 0 && (
                    <div className="citations-container">
                      <div className="citations-header">
                        <span className="citations-icon">📑</span>
                        <span>Sources & Citations ({m.citations.length})</span>
                      </div>
                      <div className="citations-chips">
                        {m.citations.map((c, cIdx) => (
                          <button
                            key={cIdx}
                            className={`citation-chip ${selectedCitation?.chunk_index === c.chunk_index && selectedCitation?.document_id === c.document_id ? "active" : ""}`}
                            onClick={() =>
                              setSelectedCitation(
                                selectedCitation?.chunk_index === c.chunk_index && selectedCitation?.document_id === c.document_id
                                  ? null
                                  : c
                              )
                            }
                          >
                            <span className="citation-doc-name">{c.filename}</span>
                            <span className="citation-page-badge">p. {c.page_number}</span>
                          </button>
                        ))}
                      </div>

                      {/* Expanded Citation Preview */}
                      {selectedCitation && m.citations.includes(selectedCitation) && (
                        <div className="citation-preview-card">
                          <div className="preview-top">
                            <span className="preview-source">
                              📄 {selectedCitation.filename} — Page {selectedCitation.page_number} (Chunk #{selectedCitation.chunk_index})
                            </span>
                            <button
                              className="btn-close-preview"
                              onClick={() => setSelectedCitation(null)}
                            >
                              ✕
                            </button>
                          </div>
                          <div className="preview-excerpt">
                            "{selectedCitation.excerpt}"
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}

          {isAsking && (
            <div className="message-row message-assistant">
              <div className="message-avatar">◈</div>
              <div className="message-bubble message-thinking">
                <div className="thinking-dots">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
                <span className="thinking-text">Searching indexed knowledge & formulating response...</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div className="chat-input-area">
          <form onSubmit={handleSubmit} className="chat-input-form">
            <textarea
              ref={textareaRef}
              rows={1}
              value={inputQuestion}
              onChange={(e) => setInputQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask any question about your institutional documents... (Press Enter to submit)"
              disabled={isAsking}
            />
            <button
              type="submit"
              className="btn-primary btn-send"
              disabled={isAsking || !inputQuestion.trim()}
            >
              {isAsking ? "..." : "Ask →"}
            </button>
          </form>
          <div className="input-disclaimer">
            DocQA retrieves excerpts directly from your institution's indexed documents with verifiable citations.
          </div>
        </div>
      </main>
    </div>
  );
}
