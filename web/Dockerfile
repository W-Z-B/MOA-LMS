# Production web bundle for the Compose stack (deploy/compose.prod.yml). The first stage builds the static
# files; the second carries only those files and a copy script, with no Node, npm or source. It copies the
# bundle into the volume that Caddy serves, then exits. The single-container image for Railway builds the
# same bundle in its own first stage (deploy/railway/Dockerfile).
# Build context is web/:  docker build -t gsa-lms-web ./web

FROM node:22-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM alpine:3
COPY --from=build /web/dist /dist
COPY scripts/publish-web.sh /usr/local/bin/publish-web
RUN chmod +x /usr/local/bin/publish-web
CMD ["publish-web"]
