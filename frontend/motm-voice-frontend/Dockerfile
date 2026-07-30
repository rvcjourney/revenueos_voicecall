FROM node:20-alpine
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 6001

# Use 700 MB heap so esbuild doesn't get killed under load
CMD ["node", "--max-old-space-size=700", "node_modules/.bin/vite", "dev", "--host", "0.0.0.0", "--port", "6001"]
