"""Deterministic parsing of spoken due dates.

LLMs are unreliable at calendar arithmetic, so the model passes the phrase the user said
("tomorrow", "next friday", "in 3 days") and we resolve it here.
"""

import re
from datetime import date, timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}


def parse_due_date(text: str, today: date) -> date:
    phrase = re.sub(r"[^\w\s-]", "", text.strip().lower())
    phrase = re.sub(r"^(on|by|for|due)\s+", "", phrase)

    try:
        return date.fromisoformat(phrase)
    except ValueError:
        pass

    if phrase in ("today", "tonight", "end of day", "eod"):
        return today
    if phrase == "tomorrow":
        return today + timedelta(days=1)
    if phrase in ("day after tomorrow", "the day after tomorrow"):
        return today + timedelta(days=2)
    if phrase == "next week":
        return today + timedelta(days=7 - today.weekday())  # next Monday
    if phrase in ("end of week", "end of the week", "this week"):
        return today + timedelta(days=max(0, 4 - today.weekday()))  # this Friday

    if match := re.fullmatch(r"in (\w+) (day|days|week|weeks)", phrase):
        count = _NUMBER_WORDS.get(match[1]) or (int(match[1]) if match[1].isdigit() else None)
        if count is not None:
            return today + timedelta(days=count * (7 if match[2].startswith("week") else 1))

    if match := re.fullmatch(r"(this |next )?(" + "|".join(WEEKDAYS) + ")", phrase):
        target = WEEKDAYS.index(match[2])
        ahead = (target - today.weekday()) % 7 or 7
        if match[1] == "next " and target > today.weekday():
            # "next friday" said on a Monday usually means the Friday of next week
            ahead += 7
        return today + timedelta(days=ahead)

    raise ValueError(
        f"Couldn't understand the date '{text}'. Use a phrase like 'tomorrow', 'next friday' or YYYY-MM-DD."
    )
