FROM python3.11-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv.sync --frozen

COPY . .

CMD ["uv", "run", "uvicorn", "apps.api.app:app", "--host", "0.0.0.0", "--port", "8000"]