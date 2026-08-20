# syntax=docker/dockerfile:1.7
FROM node:20-alpine

WORKDIR /app

# Install dependencies first for better layer caching.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copy the rest of the frontend source.
COPY frontend/ ./

EXPOSE 5173

# Run the Vite dev server only (NOT the top-level `dev` script, which also
# spawns uvicorn — that job is owned by the `backend` service in compose).
CMD ["npm", "run", "dev:frontend", "--", "--host", "0.0.0.0", "--port", "5173"]
