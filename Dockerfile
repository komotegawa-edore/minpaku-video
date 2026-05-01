FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir -e .

EXPOSE 8501

CMD ["streamlit", "run", "src/minpaku_video/app.py", \
     "--server.headless=true", \
     "--server.address=0.0.0.0", \
     "--server.port=8501"]
