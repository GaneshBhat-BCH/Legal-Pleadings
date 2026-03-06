# Use official lightweight Python image
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Copy requirements file to leverage Docker layer caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend codebase
COPY . .

# Expose the API port
EXPOSE 8000

# Command to run the application (host 0.0.0.0 is critical for Docker port forwarding)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
