from fastapi.templating import Jinja2Templates
import datetime as dt

templates = Jinja2Templates(directory="app/templates")


def datetime_to_date(value: dt.datetime):
    return f"{value:%Y-%m-%d}"


templates.env.filters["datetime_to_date"] = datetime_to_date
