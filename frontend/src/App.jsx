import { useEffect, useRef, useState } from "react";
import { checkHealth } from "./api";
import marlabsLogo from "./assets/marlabs-logo.png";
import ChatPanel from "./components/ChatPanel";
import Dashboard from "./components/Dashboard";
import Sidebar from "./components/Sidebar";
import { useChatHistory } from "./hooks/useChatHistory";

const HERO_COPY = {
  chat: {
    title: "Delivery Assistant",
    subtitle:
      "Request templates, check client status, and file completed documents — all phase-gated automatically.",
  },
  dashboard: {
    title: "Client Portfolio",
    subtitle:
      "Every client’s phase progress at a glance, with stale clients flagged automatically.",
  },
};

function extractText(content) {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .filter((block) => block.type === "text")
      .map((block) => block.text)
      .join("\n");
  }
  return "";
}

export default function App() {
  const [backendUp, setBackendUp] = useState(null);
  const [view, setView] = useState("chat");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [sidebarDrawerOpen, setSidebarDrawerOpen] = useState(false);

  // Chat session state lives here (not inside ChatPanel) because the sidebar's
  // history list and the chat panel's messages both need to read/drive the same
  // active conversation — e.g. clicking a past chat in the sidebar has to load
  // it into the chat panel, and every new exchange has to update the sidebar's
  // list. ChatPanel still owns everything else (input, sending, drag/drop,
  // upload/delete confirm flows) — only the shared conversation state moved up.
  const [messages, setMessages] = useState([]);
  const [chatId, setChatId] = useState(null);
  const chatIdRef = useRef(null);
  const {
    entries: chatHistory,
    saveEntry,
    renameEntry,
    deleteEntry,
  } = useChatHistory();

  useEffect(() => {
    checkHealth().then(setBackendUp);
  }, []);

  // Auto-save to the sidebar's history after every exchange that has real user
  // content — a fresh chatId is minted on the first user message, so reloads/
  // edits to the same conversation update one entry instead of piling up
  // duplicates.
  useEffect(() => {
    const userMessages = messages.filter((m) => m.role === "user");
    if (userMessages.length === 0) return;

    if (!chatIdRef.current) {
      chatIdRef.current = Date.now();
      setChatId(chatIdRef.current);
    }
    const title =
      extractText(userMessages[0].content).slice(0, 60) || "New chat";
    saveEntry(chatIdRef.current, title, messages);
  }, [messages, saveEntry]);

  function handleNewChat() {
    chatIdRef.current = null;
    setChatId(null);
    setMessages([]);
    setView("chat");
  }

  function handleLoadChat(entry) {
    if (chatIdRef.current === entry.id) return;
    chatIdRef.current = entry.id;
    setChatId(entry.id);
    setMessages(entry.messages);
    setView("chat");
  }

  function handleDeleteChat(id) {
    deleteEntry(id);
    if (chatIdRef.current === id) handleNewChat();
  }

  function handleRenameChat(id, title) {
    renameEntry(id, title);
  }

  const activeEntry = chatHistory.find((e) => e.id === chatId);
  const chatTitle =
    activeEntry?.title ?? (messages.length > 0 ? "New chat" : null);

  const hero = HERO_COPY[view];

  return (
    <div className="app">
      <header className="app__header">
        <button
          type="button"
          className="app__hamburger"
          title="Toggle sidebar"
          onClick={() => setSidebarDrawerOpen((v) => !v)}
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M4 7h16M4 12h16M4 17h16"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          <span className="sr-only">Toggle sidebar</span>
        </button>
        <img src={marlabsLogo} alt="Marlabs" className="app__logo" />
        <nav className="app__tabs">
          <button
            className={`app__tab ${view === "chat" ? "app__tab--active" : ""}`}
            onClick={() => setView("chat")}
          >
            Chat
          </button>
          <button
            className={`app__tab ${view === "dashboard" ? "app__tab--active" : ""}`}
            onClick={() => setView("dashboard")}
          >
            Dashboard
          </button>
        </nav>
        <span
          className={`status-dot status-dot--${backendUp ? "up" : "down"}`}
          title={backendUp ? "Backend connected" : "Backend unreachable"}
        />
      </header>
      <div className="app__hero">
        <h1>{hero.title}</h1>
        <p>{hero.subtitle}</p>
      </div>
      <div
        className={`app__body${isSidebarCollapsed ? " app__body--sidebar-collapsed" : ""}`}
      >
        <Sidebar
          entries={chatHistory}
          activeId={chatId}
          onNewChat={handleNewChat}
          onLoad={handleLoadChat}
          onDelete={handleDeleteChat}
          onRename={handleRenameChat}
          open={sidebarDrawerOpen}
          onClose={() => setSidebarDrawerOpen(false)}
        />
        <button
          type="button"
          className="sidebar-toggle"
          aria-label="Toggle Chat History"
          aria-expanded={!isSidebarCollapsed}
          onClick={() => setIsSidebarCollapsed((v) => !v)}
        >
          {isSidebarCollapsed ? (
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M9 6l6 6-6 6"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          ) : (
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M15 6l-6 6 6 6"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </button>
        <main className="app__main">
          {view === "chat" ? (
            <ChatPanel
              messages={messages}
              setMessages={setMessages}
              chatTitle={chatTitle}
              onRenameTitle={(title) => {
                if (chatIdRef.current) renameEntry(chatIdRef.current, title);
              }}
            />
          ) : (
            <Dashboard />
          )}
        </main>
      </div>
    </div>
  );
}
