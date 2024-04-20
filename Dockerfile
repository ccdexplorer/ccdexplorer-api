FROM tiangolo/uvicorn-gunicorn-fastapi:python3.11-slim
ADD --chmod=755 https://astral.sh/uv/install.sh /install.sh
RUN /install.sh && rm /install.sh
WORKDIR /code
COPY ./requirements.txt /code/requirements.txt
# RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
RUN /root/.cargo/bin/uv pip install --system --no-cache -r requirements.txt
COPY ./app /code/app
# COPY ./app/static/ /code/app/static/
CMD ["uvicorn", "app.main:app",  "--log-level", "info", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
