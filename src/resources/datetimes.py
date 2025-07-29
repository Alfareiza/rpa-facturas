from datetime import datetime, timezone, timedelta
from typing import LiteralString


def convert_utc_to_utc_minus_5(dt: datetime) -> datetime:
    """
    Convert a datetime string from UTC+0000 to UTC-5

    Args:
        dt (str): Datetime string in format 'Tue, 29 Jul 2025 14:51:18 +0000'

    Returns:
        datetime: Converted datetime object in UTC-5
    """
    from datetime import timezone
    utc_minus_5 = timezone(timedelta(hours=-5))
    return dt.astimezone(utc_minus_5)


def colombia_now() -> datetime:
    from pytz import timezone
    return datetime.now(tz=timezone("America/Bogota"))


def diff_dates(dt_older: datetime, dt_newer: datetime) -> LiteralString:
    """
    Calculates the absolute time difference between two datetime objects and returns it as a human-readable string.
    The output describes the difference in hours, minutes, and seconds.

    Args:
        dt_older (datetime): The first datetime object.
        dt_newer (datetime): The second datetime object.

    Returns:
        LiteralString: A string representing the time difference in a human-readable format.
    """
    time_difference = dt_older - dt_newer
    seconds_difference = abs(time_difference.total_seconds())

    def format_time_diff(diff_seconds):
        minutes, seconds = divmod(int(diff_seconds), 60)
        hours, minutes = divmod(minutes, 60)
        parts = []

        if hours > 0:
            parts.append(f"{hours} hora{'s' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minuto{'s' if minutes != 1 else ''}")
        if seconds > 0 or not parts:
            parts.append(f"{seconds} segundo{'s' if seconds != 1 else ''}")

        return ", ".join(parts)

    return format_time_diff(seconds_difference)


if __name__ == '__main__':
    dt_older = datetime.now() - timedelta(minutes=22)
    dt_newer = datetime.now() + timedelta(minutes=2)
    print(diff_dates(dt_older, dt_newer))
