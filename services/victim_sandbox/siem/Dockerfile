FROM python:3.11-slim

RUN useradd --system --uid 1003 --no-create-home siemuser \
 && apt-get update \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitor.py .

CMD ["python", "-u", "monitor.py"]
