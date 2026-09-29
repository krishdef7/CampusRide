FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install -e . aiohttp uvloop
COPY db ./db
COPY web ./web
COPY loadtest ./loadtest
EXPOSE 8000
CMD ["uvicorn", "campusride.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", "--loop", "uvloop", "--http", "httptools", "--no-access-log", "--log-level", "warning"]
