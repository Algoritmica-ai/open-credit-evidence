# OpenCredit Evidence — local CLI image
# Primary runtime is venv or docker compose (see docs/runtime.md).
# Not an HTTP server. Not hosted on Axis/Curiosity.

FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
COPY tests ./tests
COPY cases ./cases

RUN pip install --no-cache-dir -e ".[dev]"

# Smoke entrypoint: prove the CLI installed. Override with compose run.
CMD ["oce", "--help"]
