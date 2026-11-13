import math
import datetime as dt


def find_four_week_range(month: int, year: int) -> tuple[str]:

    # variation of Zeller's congruence, simplified for 2000 <= year <= 2099
    # source: page 95 of "The Perfect Sausage" by Kjartan Poskitt
    f = (14 - month) // 12
    y = year - f
    m = month + 12 * f - 2
    d = (y + 31 * m // 12 + y // 4) % 7  # d = 0 for Sunday, d = 1 for Monday, d = 2 for Tuesday, ...
    first_of_month = dt.date(year, month, 1)

    days_in_month = (first_of_month.replace(month=month % 12 + 1, day=1) - dt.timedelta(days=1)).day
    if d + days_in_month > 35:
        start_date = first_of_month + dt.timedelta(days=(9 - d))
        end_date = start_date + dt.timedelta(days=28)
    else:
        start_date = first_of_month + dt.timedelta(days=(1 - d))
        end_date = start_date + dt.timedelta(days=28)

    return start_date.strftime("%d/%m/%Y"), end_date.strftime("%d/%m/%Y")


for month in range(1, 13):
    for year in range(2024, 2030):
        print(f"{month}/{year}: {find_four_week_range(month, year)}")
