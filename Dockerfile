# syntax=docker/dockerfile:1.7
# Two stages: build a virtualenv from a hashed lock file, then copy it into a slim runtime
# that runs as an unprivileged user with a read-only root filesystem (see docker-compose.yml).

ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70

FROM ${PYTHON_IMAGE} AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.lock ./
RUN pip install --require-hashes --no-deps -r requirements.lock
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-deps .

FROM ${PYTHON_IMAGE} AS runtime
LABEL org.opencontainers.image.title="governed-mcp-gateway" \
      org.opencontainers.image.description="Governed MCP servers for operations tooling" \
      org.opencontainers.image.licenses="MIT"
RUN groupadd --system --gid 10001 mcp \
 && useradd --system --uid 10001 --gid mcp --no-create-home --shell /usr/sbin/nologin mcp
COPY --from=build /opt/venv /opt/venv
COPY --chown=root:root policies /app/policies
COPY --chown=root:root runbooks /app/runbooks
WORKDIR /app
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GOVERNED_MCP_HOST=0.0.0.0 \
    GOVERNED_MCP_PORT=8000 \
    GOVERNED_MCP_POLICY_DIR=/app/policies \
    GOVERNED_MCP_RUNBOOK_DIR=/app/runbooks \
    GOVERNED_MCP_AUDIT_LOG=-
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]
ENTRYPOINT ["governed-mcp", "serve"]
CMD ["tickets", "--transport", "http"]
