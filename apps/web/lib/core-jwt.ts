import "server-only";

import { randomUUID } from "node:crypto";
import { SignJWT } from "jose";

import { MIN_SECRET_LENGTH } from "./auth-config";

/** Thời hạn JWT web→core (giây). Core từ chối exp-iat > 120. */
export const CORE_TOKEN_TTL_SECONDS = 60;

export const CORE_JWT_ISSUER = "builder-web";
export const CORE_JWT_AUDIENCE = "builder-core";

/**
 * Ký JWT HS256 cho MỘT lời gọi core (khớp apps/core/app/core/auth.py). Đúng 7 claim: iss, aud,
 * sub, sv, iat, exp, jti. Không đưa email/role vào token; không tái dùng, không log.
 */
export async function signCoreToken(
  claims: { uid: string; sv: number },
  secret: string | undefined = process.env.CORE_JWT_SECRET,
): Promise<string> {
  if (!secret || secret.length < MIN_SECRET_LENGTH) {
    throw new Error("CORE_JWT_SECRET thiếu hoặc ngắn hơn 32 ký tự");
  }
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({ sv: claims.sv })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuer(CORE_JWT_ISSUER)
    .setAudience(CORE_JWT_AUDIENCE)
    .setSubject(claims.uid)
    .setIssuedAt(now)
    .setExpirationTime(now + CORE_TOKEN_TTL_SECONDS)
    .setJti(randomUUID())
    .sign(new TextEncoder().encode(secret));
}
