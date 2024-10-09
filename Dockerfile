FROM tiangolo/uvicorn-gunicorn-fastapi:python3.11
WORKDIR /code
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
COPY ./app /code/app
COPY ./app/templates/ /code/app/templates/
COPY ./app/static/ /code/app/static/
COPY ./custom_scss /code/custom_scss
COPY ./node_modules/bootstrap-icons/font/bootstrap-icons.min.css /code/node_modules/bootstrap-icons/font/bootstrap-icons.min.css
COPY ./node_modules/bootstrap-icons/font/fonts /code/node_modules/bootstrap-icons/font/fonts
COPY ./node_modules/bootstrap/dist/js/bootstrap.bundle.min.js /code/node_modules/bootstrap/dist/js/bootstrap.bundle.min.js
# COPY ./node_modules/plotly.js-dist/plotly.js /code/node_modules/plotly.js-dist/plotly.js
COPY ./node_modules/htmx.org/dist/htmx.js /code/node_modules/htmx.org/dist/htmx.js

CMD ["uvicorn", "app.main:app",  "--log-level", "warning", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
