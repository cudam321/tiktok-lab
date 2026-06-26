import { useEffect, useState, useRef } from "react";
import { api, type InsightResponse } from "@/lib/api";
import {
  Send,
  Bell,
  Zap,
  FileText,
  Lightbulb,
  FlaskConical,
  RefreshCw,
  CheckCircle2,
} from "lucide-react";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

export default function Agent() {
  const [tab, setTab] = useState<"chat" | "insights">("chat");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Agent</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            AI-powered analyst with 8 database tools
          </p>
        </div>
        <div className="flex gap-1 bg-gray-900 p-1 rounded-lg">
          <button
            onClick={() => setTab("chat")}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === "chat" ? "bg-gray-800 text-white" : "text-gray-500 hover:text-gray-300"
            }`}
          >
            Chat
          </button>
          <button
            onClick={() => setTab("insights")}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === "insights" ? "bg-gray-800 text-white" : "text-gray-500 hover:text-gray-300"
            }`}
          >
            Insights
          </button>
        </div>
      </div>

      {tab === "chat" ? <ChatPanel /> : <InsightsPanel />}
    </div>
  );
}

// --- Chat Panel ---

function ChatPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const msg = input.trim();
    if (!msg || sending) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: msg, timestamp: new Date() }]);
    setSending(true);

    try {
      const { response } = await api.agentChat(msg);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: response, timestamp: new Date() },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${e instanceof Error ? e.message : "Failed to get response"}`,
          timestamp: new Date(),
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl flex flex-col" style={{ height: "calc(100vh - 220px)" }}>
      {/* Messages */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center py-16 text-gray-600">
            <p className="text-lg mb-2">Ask the agent anything</p>
            <div className="flex flex-wrap justify-center gap-2 max-w-md mx-auto">
              {[
                "How are my accounts doing?",
                "Which posts performed best this week?",
                "Suggest an experiment to run",
                "What should I post next on Account 1?",
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => setInput(suggestion)}
                  className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 px-3 py-1.5 rounded-full transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] rounded-xl px-4 py-2.5 text-sm ${
                msg.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-800 text-gray-200"
              }`}
            >
              <div className="whitespace-pre-wrap">{msg.content}</div>
              <div
                className={`text-xs mt-1 ${
                  msg.role === "user" ? "text-blue-300" : "text-gray-500"
                }`}
              >
                {msg.timestamp.toLocaleTimeString("en-US", {
                  hour: "numeric",
                  minute: "2-digit",
                })}
              </div>
            </div>
          </div>
        ))}

        {sending && (
          <div className="flex justify-start">
            <div className="bg-gray-800 rounded-xl px-4 py-3 text-sm text-gray-400">
              <div className="flex items-center gap-2">
                <div className="animate-pulse">Thinking...</div>
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSend} className="p-4 border-t border-gray-800">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your accounts, metrics, or experiments..."
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            disabled={sending}
          />
          <button
            type="submit"
            disabled={!input.trim() || sending}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed px-4 py-2.5 rounded-lg transition-colors"
          >
            <Send size={16} />
          </button>
        </div>
      </form>
    </div>
  );
}

// --- Insights Panel ---

function InsightsPanel() {
  const [insights, setInsights] = useState<InsightResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);

  async function loadInsights() {
    setLoading(true);
    try {
      const data = await api.getInsights();
      setInsights(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadInsights();
  }, []);

  async function handleTrigger(type: "briefing" | "scan") {
    setTriggering(true);
    try {
      if (type === "briefing") {
        await api.triggerBriefing();
      } else {
        await api.triggerScan();
      }
      await loadInsights();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed");
    } finally {
      setTriggering(false);
    }
  }

  async function handleMarkRead(id: number) {
    await api.markInsightRead(id);
    setInsights((prev) => prev.map((i) => (i.id === id ? { ...i, is_read: true } : i)));
  }

  const insightIcon = (type: InsightResponse["type"]) => {
    switch (type) {
      case "briefing": return <FileText size={16} />;
      case "alert": return <Zap size={16} />;
      case "suggestion": return <Lightbulb size={16} />;
      case "experiment_result": return <FlaskConical size={16} />;
    }
  };

  const priorityColor = (p: InsightResponse["priority"]) => {
    switch (p) {
      case "critical": return "border-red-500 bg-red-400/5";
      case "high": return "border-orange-500 bg-orange-400/5";
      case "medium": return "border-blue-500/30 bg-gray-900";
      case "low": return "border-gray-800 bg-gray-900";
    }
  };

  return (
    <div className="space-y-4">
      {/* Actions */}
      <div className="flex gap-2">
        <button
          onClick={() => handleTrigger("briefing")}
          disabled={triggering}
          className="flex items-center gap-2 bg-gray-800 hover:bg-gray-700 px-3 py-2 rounded-lg text-sm text-gray-300 transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={triggering ? "animate-spin" : ""} />
          Generate Briefing
        </button>
        <button
          onClick={() => handleTrigger("scan")}
          disabled={triggering}
          className="flex items-center gap-2 bg-gray-800 hover:bg-gray-700 px-3 py-2 rounded-lg text-sm text-gray-300 transition-colors disabled:opacity-50"
        >
          <Bell size={14} />
          Run Anomaly Scan
        </button>
      </div>

      {/* Insights List */}
      {loading ? (
        <div className="text-gray-500 text-center py-12 animate-pulse">Loading...</div>
      ) : insights.length === 0 ? (
        <div className="text-center py-16 text-gray-600">
          <p className="text-lg mb-1">No insights yet</p>
          <p className="text-sm">Generate a briefing or wait for scheduled scans.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {insights.map((insight) => (
            <div
              key={insight.id}
              className={`border rounded-xl p-4 transition-colors ${priorityColor(insight.priority)} ${
                !insight.is_read ? "" : "opacity-60"
              }`}
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-gray-400">{insightIcon(insight.type)}</span>
                  <span className="text-xs text-gray-500 uppercase">{insight.type}</span>
                  {!insight.is_read && (
                    <span className="w-2 h-2 rounded-full bg-blue-500" />
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500">
                    {new Date(insight.created_at).toLocaleString("en-US", {
                      month: "short",
                      day: "numeric",
                      hour: "numeric",
                      minute: "2-digit",
                    })}
                  </span>
                  {!insight.is_read && (
                    <button
                      onClick={() => handleMarkRead(insight.id)}
                      className="text-gray-500 hover:text-emerald-400"
                      title="Mark read"
                    >
                      <CheckCircle2 size={14} />
                    </button>
                  )}
                </div>
              </div>
              <h3 className="font-medium text-white mb-1">{insight.title}</h3>
              <p className="text-sm text-gray-400 whitespace-pre-wrap">{insight.body}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
