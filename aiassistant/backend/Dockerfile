FROM python:3.10-slim

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

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Ensure the uploads directory exists
RUN mkdir -p uploads

# Expose the port Flask/Gunicorn will run on
EXPOSE 5000

# Start the application using Gunicorn, binding to the dynamic PORT provided by Render
# We use sh -c to allow environment variable expansion while keeping the exec form for signals
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} app:app --timeout 180"]
