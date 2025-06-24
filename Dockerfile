FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy your full app
COPY . .

# Expose port (for FastAPI/Uvicorn)
EXPOSE 8000

# Start your bot and web server
CMD ["python", "bot.py"]  # Change to your actual script name
