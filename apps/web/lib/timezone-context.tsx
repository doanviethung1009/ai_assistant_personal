"use client";

import { createContext, useContext } from "react";

const TimezoneContext = createContext<string | null>(null);

/**
 * Đưa múi giờ hiển thị (lấy ở server, từ backend hoặc file) xuống mọi client component.
 *
 * Tồn tại để server render và client hydrate dùng CÙNG một chuỗi tz: nếu client tự đoán
 * (múi giờ browser) thì giờ hiển thị lệch và React báo hydration mismatch.
 */
export function TimezoneProvider({
  tz,
  children,
}: Readonly<{ tz: string; children: React.ReactNode }>) {
  return <TimezoneContext.Provider value={tz}>{children}</TimezoneContext.Provider>;
}

/** Múi giờ hiển thị hiện hành. Ném lỗi nếu quên bọc TimezoneProvider ở layout. */
export function useDisplayTz(): string {
  const tz = useContext(TimezoneContext);
  if (tz === null) {
    throw new Error("useDisplayTz phải dùng bên trong <TimezoneProvider> (app/layout.tsx)");
  }
  return tz;
}
