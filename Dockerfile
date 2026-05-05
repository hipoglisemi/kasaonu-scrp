FROM python:3.10-slim

# Install system dependencies for Chromium and Selenium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    chromium \
    chromium-driver \
    libnss3 \
    libgconf-2-4 \
    libxss1 \
    libasound2 \
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
# Tell Selenium to use the installed Chromium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

EXPOSE 8001

# Health check for Coolify
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

# Run the repair API
CMD ["python", "repair_api.py"]
