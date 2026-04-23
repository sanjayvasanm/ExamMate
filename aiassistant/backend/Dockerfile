# Use a specific version for stability
FROM python:3.10-slim

# Memory optimization environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MALLOC_ARENA_MAX=2 \
    PORT=10000

# Install system dependencies for PaddleOCR and standard tools
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install with memory efficiency
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Ensure the uploads directory exists
RUN mkdir -p uploads

# Expose the port (Render uses $PORT)
EXPOSE 10000

# Start with a single worker to stay within 512MB RAM limit
# We use threads instead of workers for better memory sharing
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} app:app --workers 1 --threads 2 --timeout 120 --log-level info"]
