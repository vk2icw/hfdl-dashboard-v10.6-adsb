FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY LICENSE DISCLAIMER.md PRIVACY.md SECURITY.md THIRD_PARTY_NOTICES.md CHANGELOG.md VERSION README.md ./
EXPOSE 8090/tcp 5557/udp
CMD ["python", "app.py"]
