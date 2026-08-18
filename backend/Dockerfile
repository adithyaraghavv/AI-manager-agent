# Minimal container for the PM Document Assistant FastAPI backend.
FROM python:3.13-slim

# Non-interactive apt and unbuffered Python I/O for cleaner container logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

# Install uv (project-standard Python tooling).
RUN pip install --no-cache-dir uv==0.5.11

# Copy backend source (build context is the repo root; see package.yml).
COPY backend/ /app/

# Install runtime deps into the system interpreter using uv.
RUN uv pip install --system -r /app/requirements.txt

EXPOSE 8000

# The FastAPI app object lives in backend/main.py as `app`.
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
