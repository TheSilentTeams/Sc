# Use official Python base with Debian (Playwright needs system libs)
FROM python:3.10-slim

# Install dependencies required by Playwright
RUN apt-get update && apt-get install -y \
    wget \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libxshmfence1 \
    libxext6 \
    libxfixes3 \
    fonts-liberation \
    libdrm2 \
    libatk1.0-0 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN python -m playwright install --with-deps

# Copy rest of the app
COPY . .

# Expose port (if running a web app)


# Run your app (adjust this as needed)
CMD ["python", "app.py"]
