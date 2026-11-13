import math
import datetime as dt


def find_four_week_range(month: int, year: int) -> tuple[str]:

    # variation of Zeller's congruence
    # source: page 95 of "The Perfect Sausage" by Kjartan Poskitt
    f = (14 - month) // 12
    y = year - f
    m = month + 12 * f - 2
    d = (y + 31 * m // 12 + y // 4) % 7  # d = 0 for Sunday, d = 1 for Monday, d = 2 for Tuesday, ...
    first_of_month = dt.date(year, month, 1)

    if 5 <= d <= 6:
        start_date = first_of_month + dt.timedelta(days=(9 - d))
        end_date = start_date + dt.timedelta(days=28)
    else:
        start_date = first_of_month + dt.timedelta(days=(1 - d))
        end_date = start_date + dt.timedelta(days=28)

    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")


print(find_four_week_range(10, 2026))  # Example usage
