"""Clock-skew allowance shared by record checks and hook diagnostics."""

import datetime as dt


FUTURE_TOLERANCE = dt.timedelta(minutes=5)
