# Hugging Face Space image — Docker SDK.
#
# Spaces runs the container as uid 1000 with a read-only image layer, so
# anything the app writes — uploaded packs, runs, the tamper-demo copy, a
# rebuilt corpus index — lives in a workspace the app user owns. It is wiped
# when the Space restarts, which is the right behaviour for a shared demo.
#
# Models: the Space cannot reach the team's GPU node, so every role runs on
# NVIDIA Build. NVIDIA_API_KEY is a Space secret, set in the Space settings —
# never in this file. Without it, everything but "Run" works: browsing packs
# and cases, the committed evidence packs, verify, the tamper demo.

FROM python:3.12-slim

RUN useradd --create-home --uid 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /home/user/app

COPY --chown=user pyproject.toml README.md LICENSE NOTICE THIRD_PARTY_NOTICES.md ./
COPY --chown=user src ./src
COPY --chown=user packs ./packs
COPY --chown=user regulations ./regulations
COPY --chown=user runs ./runs
COPY --chown=user specs ./specs
RUN pip install --no-cache-dir --user '.[web]'

ENV EVIDENCE_ROOT=/home/user/app \
    EVIDENCE_WORKSPACE=/home/user/workspace \
    EVIDENCE_SHARED=1

EXPOSE 7860
CMD ["evidence", "ui", "--host", "0.0.0.0", "--port", "7860"]
