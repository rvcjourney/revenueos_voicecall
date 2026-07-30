FROM node:20-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Vite embeds VITE_* vars into the bundle at build time, so this must be
# passed as a build arg (see docker-compose.yml), not a runtime env var.
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

# Use 700 MB heap so tsc/esbuild/rollup don't get killed under load
ENV NODE_OPTIONS=--max-old-space-size=700
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app

RUN npm install -g serve@14
COPY --from=builder /app/dist ./dist

EXPOSE 6001

# Serve the pre-built static bundle instead of running the dev server in
# production. -s enables SPA fallback so client-side routes (e.g. /dashboard)
# still resolve on a hard refresh.
CMD ["serve", "-s", "dist", "-l", "6001"]
