# MinIO's public images and binaries were withdrawn when the open-source
# project was archived, so the same release this stack has always used is
# built here from the source still on GitHub. Internal-only: no port is
# published (see docker-compose.yml).
FROM golang:1.23-bookworm AS builder

ARG MINIO_RELEASE=RELEASE.2024-11-07T00-52-20Z

RUN git clone --depth 1 --branch "${MINIO_RELEASE}" https://github.com/minio/minio.git /src
WORKDIR /src
RUN CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o /minio .


FROM debian:bookworm-slim

# curl: used by the compose healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /minio /usr/bin/minio

VOLUME ["/data"]
EXPOSE 9000 9001

ENTRYPOINT ["/usr/bin/minio"]
