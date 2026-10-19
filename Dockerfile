FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY collector.py season_admin.py probe_stats.py stats.py ./
CMD ["python", "collector.py"]
