FROM python:3.12-slim

WORKDIR /app

RUN pip install --quiet uv

COPY pyproject.toml .
COPY src/ src/

RUN uv pip install --system ".[aws]"

COPY catalogs/ catalogs/

EXPOSE 8000

CMD ["moon", "serve", "--host", "0.0.0.0", "--port", "8000"]
