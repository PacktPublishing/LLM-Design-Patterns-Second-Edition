FROM python:3.12-slim

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin policyops
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY labs ./labs

RUN pip install --no-cache-dir . \
    && chown -R policyops:policyops /app

USER policyops
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "policyops.api:app", "--host", "0.0.0.0", "--port", "8080"]
