FROM tiangolo/uvicorn-gunicorn-fastapi:python3.11-slim
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"
WORKDIR /code
COPY ./requirements.txt /code/requirements.txt
RUN uv venv \
    && uv pip sync --system --no-cache requirements.txt
# RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
COPY ./app /code/app
# COPY ./app/static/ /code/app/static/
CMD ["uvicorn", "app.main:app",  "--log-level", "info", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
