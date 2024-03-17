FROM python:3.11

# Create a directory for the app
WORKDIR /app
# Install the necessary packages
RUN pip install ccxt requests Telethon
# Add the main.py and config.json to the Docker image
COPY main.py .
COPY config.json .

CMD ["python", "./main.py"]