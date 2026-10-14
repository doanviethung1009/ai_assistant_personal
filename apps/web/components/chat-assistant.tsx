"use client";

import React, { useState, useEffect, useRef } from "react";
import { Bot, X, Send, Command, Loader2 } from "lucide-react";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

export function ChatAssistant() {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      role: "assistant",
      content: "Xin chào! Tôi là Builder AI Assistant. Nhấn `Cmd + K` hoặc gọi tôi để quản lý Task, Note hoặc tính toán dữ liệu nhé.",
    },
  ]);
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const streamRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Dọn timer mock khi component unmount, tránh setState sau khi đã gỡ.
  useEffect(() => () => {
    if (streamRef.current) clearInterval(streamRef.current);
  }, []);

  // Toggle bằng Cmd+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Cuộn xuống dòng tin nhắn mới nhất
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isOpen, isTyping]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage: Message = { id: Date.now().toString(), role: "user", content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsTyping(true);

    // Mock luồng xử lý Streaming từ Backend (RAG + AI)
    setTimeout(() => {
      let mockResponse = "Dựa trên các ghi chú và công việc hiện tại, hệ thống đang được cấu hình để triển khai Phase 2. ";
      
      if (userMessage.content.toLowerCase().includes("tạo task")) {
        mockResponse = "Đã lên lệnh tạo Task thành công thông qua Action Agent! Dữ liệu đã được ghi vào PostgreSQL.";
      }
      
      const assistantId = (Date.now() + 1).toString();
      setMessages((prev) => [...prev, { id: assistantId, role: "assistant", content: "" }]);

      // Simulate streaming word by word
      const words = mockResponse.split(" ");
      let currentWordIndex = 0;

      streamRef.current = setInterval(() => {
        const word = words[currentWordIndex];
        if (word !== undefined) {
          const prefix = currentWordIndex > 0 ? " " : "";
          // Cập nhật theo id, không theo vị trí cuối mảng: tránh ghi nhầm khi có tin mới chen vào.
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + prefix + word } : m)),
          );
          currentWordIndex++;
        } else {
          if (streamRef.current) clearInterval(streamRef.current);
          setIsTyping(false);
        }
      }, 50); // 50ms per word
    }, 600);
  };

  /**
   * Render markdown tối giản (in đậm, inline code) bằng React node, KHÔNG dùng
   * dangerouslySetInnerHTML: nội dung sau này tới từ LLM/RAG nên là untrusted,
   * JSX tự escape nên không có đường XSS.
   */
  const renderContent = (content: string) =>
    content.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
        return <strong key={i}>{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
        return (
          <code key={i} className="rounded bg-[var(--color-surface-raised)] px-1 py-0.5 text-[var(--color-accent)]">
            {part.slice(1, -1)}
          </code>
        );
      }
      return <span key={i}>{part}</span>;
    });

  return (
    <>
      {/* Nút gọi AI khi đóng */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-tr from-blue-600 to-indigo-500 text-white shadow-2xl transition-transform hover:scale-110 active:scale-95"
          aria-label="Mở AI Assistant"
        >
          <Bot className="h-6 w-6" />
        </button>
      )}

      {/* Drawer Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-[var(--color-surface)]/20 backdrop-blur-sm transition-opacity"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* Chat Drawer */}
      <div
        className={`fixed bottom-0 right-0 top-0 z-50 flex w-full max-w-md transform flex-col bg-[var(--color-surface-raised)]/90 shadow-2xl ring-1 ring-[var(--color-border)] backdrop-blur-xl transition-transform duration-300 ease-in-out sm:right-6 sm:top-6 sm:h-[calc(100vh-3rem)] sm:rounded-2xl ${
          isOpen ? "translate-x-0" : "translate-x-[120%]"
        }`}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-[var(--color-border)]/50 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-tr from-blue-600/20 to-indigo-500/20 text-blue-500 ring-1 ring-blue-500/30">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-[var(--color-ink)]">Builder AI</h2>
              <p className="flex items-center gap-1 text-xs text-[var(--color-ink-muted)]">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75"></span>
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500"></span>
                </span>
                Multi-Agent System Active
              </p>
            </div>
          </div>
          <button
            onClick={() => setIsOpen(false)}
            className="rounded-full p-2 text-[var(--color-ink-muted)] transition-colors hover:bg-[var(--color-surface)] hover:text-[var(--color-ink)]"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Message List */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow-sm ${
                  msg.role === "user"
                    ? "bg-[var(--color-ink)] text-[var(--color-surface)] rounded-tr-sm"
                    : "bg-[var(--color-surface)] border border-[var(--color-border)]/50 text-[var(--color-ink)] rounded-tl-sm"
                }`}
              >
                {msg.role === "assistant" ? renderContent(msg.content) : msg.content}
              </div>
              <span className="mt-1 px-1 text-xs text-[var(--color-ink-muted)] opacity-70">
                {msg.role === "user" ? "Bạn" : "AI"}
              </span>
            </div>
          ))}
          {isTyping && (
            <div className="flex items-start">
              <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm bg-[var(--color-surface)] border border-[var(--color-border)]/50 px-4 py-3 shadow-sm">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--color-ink-muted)]" style={{ animationDelay: "0ms" }}></span>
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--color-ink-muted)]" style={{ animationDelay: "150ms" }}></span>
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--color-ink-muted)]" style={{ animationDelay: "300ms" }}></span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="shrink-0 border-t border-[var(--color-border)]/50 p-4">
          <form onSubmit={handleSubmit} className="relative flex items-center">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask AI anything..."
              className="w-full rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] py-3 pl-5 pr-12 text-sm text-[var(--color-ink)] placeholder-[var(--color-ink-muted)] shadow-inner focus:border-blue-500/50 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              disabled={isTyping}
            />
            <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
              {input.length === 0 && !isTyping ? (
                <div className="hidden items-center gap-1 rounded bg-[var(--color-surface-raised)] px-1.5 py-1 text-xs text-[var(--color-ink-muted)] sm:flex border border-[var(--color-border)]/50">
                  <Command className="h-3 w-3" /> K
                </div>
              ) : null}
              <button
                type="submit"
                disabled={!input.trim() || isTyping}
                className={`flex h-8 w-8 items-center justify-center rounded-full transition-all ${
                  input.trim() && !isTyping
                    ? "bg-blue-600 text-white shadow-md hover:bg-blue-700"
                    : "bg-[var(--color-surface-raised)] text-[var(--color-ink-muted)]"
                }`}
              >
                {isTyping ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4 ml-0.5" />}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
