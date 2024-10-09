from fastapi.templating import Jinja2Templates
import datetime as dt
import humanize

templates = Jinja2Templates(directory="app/templates")


def datetime_to_date(value: dt.datetime):
    return f"{value:%Y-%m-%d}"


def datetime_to_date_and_time_no_sec(value: dt.datetime):
    return f"{value:%Y-%m-%d %H:%M} UTC"


def seperator_no_decimals(value: int):
    return f"{int(value):,.0f}"


def humanize_timedelta(value: dt.datetime):
    return humanize.precisedelta(value, suppress=["days"], format="%0.0f")


templates.env.filters["datetime_to_date"] = datetime_to_date
templates.env.filters["datetime_to_date_and_time_no_sec"] = (
    datetime_to_date_and_time_no_sec
)
templates.env.filters["seperator_no_decimals"] = seperator_no_decimals

templates.env.filters["humanize_timedelta"] = humanize_timedelta
