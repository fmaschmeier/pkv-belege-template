FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY api/requirements.txt ./api/
RUN pip install --no-cache-dir -r api/requirements.txt

# Copy parser modules (needed by API)
COPY parser.py .
COPY bank_parser.py .
COPY receipt_parser.py .

# Copy API code
COPY api/app ./api/app

# Create cache directory
RUN mkdir -p .cache

# Set environment
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Run with uvicorn
CMD exec uvicorn api.app.main:app --host 0.0.0.0 --port ${PORT}
