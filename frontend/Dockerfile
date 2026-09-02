# =====================================================================
# Frontend image — Next.js 16 (App Router)
# Three stages. Only the last one ships: it holds the compiled app and a
# minimal node_modules, not the 500 MB dev tree.
# =====================================================================

# ------------------------------------------------------------------ deps
FROM node:22-alpine AS deps
WORKDIR /app

# Lockfile first — cached until dependencies actually change.
COPY package.json package-lock.json ./
RUN npm ci

# --------------------------------------------------------------- builder
FROM node:22-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
# Needs `output: "standalone"` in next.config.ts (see the guide).
RUN npm run build

# --------------------------------------------------------------- runtime
FROM node:22-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
# "standalone" is a self-contained server + only the node_modules it needs.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
