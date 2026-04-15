FROM python:3.10-slim

WORKDIR /app

# Copy only what's needed for the repair API
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Copy project files
COPY . .

# Environment
ENV PORT=8001
EXPOSE 8001

# Health check for Coolify
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

# Run the repair API
CMD ["python", "repair_api.py"]
