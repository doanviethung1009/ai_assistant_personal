"use client";

import { useState } from "react";

export function ApiTester() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-2 rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-xs font-medium text-white shadow-sm transition-colors hover:bg-[var(--color-accent-hover)]"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
        Test API (Swagger UI)
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm sm:p-6 sm:py-12">
          <div className="flex h-full w-full max-w-6xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl ring-1 ring-black/5">
            <div className="flex items-center justify-between border-b border-gray-200 bg-gray-50 px-4 py-3">
              <div>
                <h2 className="text-sm font-semibold text-gray-800">
                  Giao diện Test API Trực tiếp (Swagger)
                </h2>
                <p className="text-[10px] text-gray-500">
                  Backend phải đang chạy (localhost:8000). Mọi thao tác gửi request đều ghi trực tiếp vào Database thật của bạn.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="rounded p-1 text-gray-500 transition-colors hover:bg-gray-200 hover:text-gray-700"
                title="Đóng (Esc)"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18"></line>
                  <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
              </button>
            </div>
            <div className="flex-1 bg-white">
              <iframe
                src="http://localhost:8000/docs"
                className="h-full w-full border-0"
                title="Swagger UI"
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
