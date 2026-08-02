# =============================================================================
# Next.js production image — multi-stage.
#
# Three stages so the runtime image contains neither the npm cache, nor the
# devDependencies, nor the source tree: the final image ships only the compiled
# standalone server. That is roughly a 1.1 GB -> ~180 MB difference, which is
# real deploy time and real attack surface.
# =============================================================================

FROM node:22-alpine AS deps
WORKDIR /app
# Copy only the manifests first so this layer is cached across source changes —
# `npm ci` is by far the slowest step and it depends only on these two files.
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* is compiled into the client bundle, so it must be present at
# BUILD time — setting it only at runtime silently has no effect.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0

# Non-root. A container running as root that is compromised gives the attacker
# root inside the namespace and a much shorter path to the host.
RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "require('http').get('http://127.0.0.1:3000/dashboard',r=>process.exit(r.statusCode<400?0:1)).on('error',()=>process.exit(1))"

CMD ["node", "server.js"]
