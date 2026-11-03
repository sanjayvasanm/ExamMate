# Use a specific version for stability
FROM python:3.10-slim

# Memory optimization environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MALLOC_ARENA_MAX=2 \
    PORT=10000

# Install lightweight system dependencies
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install with memory efficiency
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the port (Render uses $PORT)
EXPOSE 10000

# Start with a single worker and threads to stay within 512MB RAM limit.
# Recycle workers via max-requests to prevent memory fragmentation and leaks.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} app:app --workers 1 --threads 2 --worker-class gthread --max-requests 50 --max-requests-jitter 10 --timeout 120 --log-level info"]
