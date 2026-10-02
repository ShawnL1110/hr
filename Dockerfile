FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Europe/Madrid
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home hr && mkdir /data && chown hr:hr /data
COPY --chown=hr:hr hr ./hr
COPY --chown=hr:hr docs ./docs
USER hr
EXPOSE 8080
CMD ["uvicorn", "hr.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
