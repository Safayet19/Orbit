# syntax=docker/dockerfile:1.7

FROM python:3.13-slim AS dependencies

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

RUN python -m venv "${VIRTUAL_ENV}"

WORKDIR /build
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

FROM python:3.13-slim AS runtime

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY --from=dependencies /opt/venv /opt/venv
COPY backend/ ./backend/
COPY alembic.ini ./alembic.ini

RUN useradd --system --uid 10001 --create-home orbit
USER 10001:10001

EXPOSE 8000
