# Credit Evidence Engine — CLI image. Not an HTTP server.
#   docker build -t credit-evidence-engine .
#   docker run --rm -e NVIDIA_API_KEY -v $PWD/runs:/app/runs credit-evidence-engine \
#       evidence run packs/underwriter-sample --repeats 3 --out runs/today
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE THIRD_PARTY_NOTICES.md ./
COPY src ./src
COPY tests ./tests
COPY packs ./packs
COPY regulations ./regulations
COPY specs ./specs
COPY scripts ./scripts
COPY runs ./runs

RUN pip install --no-cache-dir -e ".[dev]"

CMD ["evidence", "--help"]
