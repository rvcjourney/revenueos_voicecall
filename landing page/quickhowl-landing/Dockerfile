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
# One real file per route (App.tsx's CurrentRoute) so unknown paths get a real
# 404 instead of a 200 homepage, which Google flags as "Soft 404". 404.html is
# served with status 404 and still renders the site for humans.
RUN for p in privacy-policy terms-of-service 404; do cp dist/index.html dist/$p.html; done

FROM node:20-alpine AS runner
WORKDIR /app

RUN npm install -g serve@14
COPY --from=builder /app/dist ./dist

EXPOSE 6002

# No -s (SPA fallback): it answered 200 for every path. serve's cleanUrls maps
# /privacy-policy -> privacy-policy.html; anything else gets 404.html + 404.
CMD ["serve", "dist", "-l", "6002"]
