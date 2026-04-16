FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir flask psycopg2-binary requests httpx openai python-dotenv
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]
