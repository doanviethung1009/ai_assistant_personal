import { describe, expect, it } from "vitest";

import { clientIpFrom } from "@/lib/client-ip";

const h = (xff?: string) => new Headers(xff ? { "x-forwarded-for": xff } : {});

describe("clientIpFrom", () => {
  it("mặc định không tin X-Forwarded-For", () => {
    expect(clientIpFrom(h("1.2.3.4"), {})).toBeNull();
    expect(clientIpFrom(h("1.2.3.4"), { TRUST_FORWARDED_FOR: "false" })).toBeNull();
  });

  it("TRUST_FORWARDED_FOR=true, 1 hop (mặc định): lấy phần tử CUỐI do proxy tin cậy nối, bỏ phần client tự khai", () => {
    const env = { TRUST_FORWARDED_FOR: "true" };
    expect(clientIpFrom(h("6.6.6.6, 203.0.113.9 "), env)).toBe("203.0.113.9");
    expect(clientIpFrom(h("2001:db8::1"), env)).toBe("2001:db8::1");
  });

  it("TRUSTED_PROXY_HOPS=2: lấy phần tử thứ hai từ bên phải; thiếu phần tử → null", () => {
    const env = { TRUST_FORWARDED_FOR: "true", TRUSTED_PROXY_HOPS: "2" };
    expect(clientIpFrom(h("6.6.6.6, 203.0.113.9, 10.0.0.1"), env)).toBe("203.0.113.9");
    expect(clientIpFrom(h("10.0.0.1"), env)).toBeNull();
  });

  it("TRUSTED_PROXY_HOPS không hợp lệ rơi về 1", () => {
    const env = { TRUST_FORWARDED_FOR: "true", TRUSTED_PROXY_HOPS: "abc" };
    expect(clientIpFrom(h("6.6.6.6, 203.0.113.9"), env)).toBe("203.0.113.9");
  });

  it("không phải IP hoặc thiếu header → null", () => {
    const env = { TRUST_FORWARDED_FOR: "true" };
    expect(clientIpFrom(h("not-an-ip"), env)).toBeNull();
    expect(clientIpFrom(h("1.2.3.4:80"), env)).toBeNull();
    expect(clientIpFrom(h(), env)).toBeNull();
  });
});
