# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS base
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# ── Dependency ─────────────────────────────────────────────────────────
FROM base AS deps
COPY package.json package-lock.json* ./
# npm ci cần lock file; lần đầu chưa có thì fallback sang install
RUN --mount=type=cache,target=/root/.npm \
    if [ -f package-lock.json ]; then npm ci; else npm install; fi

# ── Dev: hot reload ────────────────────────────────────────────────────
FROM deps AS dev
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]

# ── Build cho prod ─────────────────────────────────────────────────────
FROM deps AS builder
# Biến NEXT_PUBLIC_* được nhúng vào bundle client lúc build, không đọc được
# ở runtime. Vì vậy phải truyền qua build arg, không phải qua environment.
ARG NEXT_PUBLIC_DISPLAY_TZ=Asia/Ho_Chi_Minh
ENV NEXT_PUBLIC_DISPLAY_TZ=$NEXT_PUBLIC_DISPLAY_TZ
COPY . .
RUN npm run build

# ── Prod: chỉ runtime standalone, user không phải root ────────────────
FROM base AS prod
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
