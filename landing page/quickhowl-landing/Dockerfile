FROM node:20-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Vite embeds VITE_* vars into the bundle at build time, so these must be
# passed as build args (see docker-compose.yml), not runtime env vars.
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
ARG VITE_EXISTING_APP_LOGIN_URL
ENV VITE_EXISTING_APP_LOGIN_URL=$VITE_EXISTING_APP_LOGIN_URL
ARG VITE_EXISTING_APP_SIGNUP_URL
ENV VITE_EXISTING_APP_SIGNUP_URL=$VITE_EXISTING_APP_SIGNUP_URL

# Use 700 MB heap so tsc/esbuild/rollup don't get killed under load
ENV NODE_OPTIONS=--max-old-space-size=700
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app

RUN npm install -g serve@14
COPY --from=builder /app/dist ./dist

EXPOSE 6002

# Serve the pre-built static bundle. -s enables SPA fallback for parity with
# the main app's Dockerfile, though this project has no client-side routes.
CMD ["serve", "-s", "dist", "-l", "6002"]
