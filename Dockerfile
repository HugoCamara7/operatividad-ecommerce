FROM python:3.11-slim

WORKDIR /srv

# Las dependencias primero: la capa se reutiliza mientras no cambien.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080
HEALTHCHECK CMD curl --fail http://localhost:8080/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8080", "--server.address=0.0.0.0", "--server.headless=true"]
