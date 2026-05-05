FROM python:3.10-slim

# Install system dependencies for Chromium and Selenium
# Minimal list for headless chromium to run on Debian
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    gnupg \
    unzip \
    chromium \
    chromium-driver \
    libnss3 \
    libxss1 \
    libasound2 \
    libgbm1 \
    libgtk-3-0 \
    fonts-liberation \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only what's needed for the repair API
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Copy project files
COPY . .

# Environment
ENV PORT=8001
ENV PYTHONUNBUFFERED=1
# Tell Selenium where the binaries are
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

# Run the repair API
CMD ["python", "repair_api.py"]
