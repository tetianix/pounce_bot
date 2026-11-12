from datetime import date, datetime, timezone

import pytest

from scrapers.olx import fix_date, format_published_date, parse_published_date


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


NOW = utc(2026, 10, 11, 9, 0)


@pytest.mark.parametrize("text, now, result", [
    ("Сьогодні о 08:56", utc(2026, 10, 11, 9, 14), "Сьогодні о 11:56"),
    ("Вчора о 12:00", utc(2026, 10, 11, 9, 14), "Вчора о 15:00"),
    ("Сьогодні о 08:56", utc(2026, 11, 15, 9, 0), "Сьогодні о 10:56"),
    ("Сьогодні о 22:30", utc(2026, 10, 11, 22, 40), "Сьогодні о 01:30"),
    ("Сьогодні о 20:30", utc(2026, 10, 11, 22, 40), "Вчора о 23:30"),
    ("Вчора о 22:30", utc(2026, 10, 11, 5, 0), "Сьогодні о 01:30"),
    ("Вчора о 08:00", utc(2026, 10, 11, 22, 30), "10 жовтня 2026 р."),
    ("Оновлено сьогодні о 08:56", utc(2026, 10, 11, 9, 14), "Оновлено сьогодні о 11:56"),
    ("09 жовтня 2026 р.", utc(2026, 10, 11, 9, 14), "09 жовтня 2026 р."),
], ids=["today-summer", "yesterday", "today-winter", "after-midnight-in-kyiv", "before-midnight-in-kyiv",
        "utc-yesterday-is-kyiv-today", "two-days-ago-full-date", "keeps-prefix", "full-date-unchanged"])
def test_fix_date_moves_utc_to_kyiv(text, now, result):
    assert fix_date(text, now) == result


@pytest.mark.parametrize("text, now, result", [
    ("Сьогодні о 11:56", NOW, date(2026, 10, 11)),
    ("Вчора о 23:30", NOW, date(2026, 10, 10)),
    ("Оновлено сьогодні о 11:56", NOW, date(2026, 10, 11)),
    ("Сьогодні о 01:30", utc(2026, 10, 11, 22, 40), date(2026, 10, 12)),
    ("09 жовтня 2026 р.", NOW, date(2026, 10, 9)),
    ("3 березня 2026 р.", NOW, date(2026, 3, 3)),
    ("09 октября 2026 г.", NOW, None),
    ("31 лютого 2026 р.", NOW, None),
    ("", NOW, None),
    (None, NOW, None),
], ids=["today", "yesterday", "prefix", "kyiv-calendar", "full-date", "single-digit-day", "unknown-month",
        "impossible-date", "empty", "none"])
def test_parse_published_date(text, now, result):
    assert parse_published_date(text, now) == result


@pytest.mark.parametrize("text, now, result", [
    ("Вчора о 23:30", NOW, "Вчора о 23:30"),
    ("Сьогодні о 11:56", NOW, "Сьогодні о 11:56"),
    ("10 жовтня 2026 р.", NOW, "Вчора"),
    ("09 жовтня 2026 р.", NOW, "Позавчора"),
    ("08 жовтня 2026 р.", NOW, "8 жовтня"),
    ("28 грудня 2025 р.", NOW, "28 грудня 2025 р."),
    ("11 жовтня 2026 р.", NOW, "Сьогодні"),
    ("11 жовтня 2026 р.", utc(2026, 10, 11, 22, 30), "Вчора"),
    ("Оновлено 10 жовтня 2026 р.", NOW, "Оновлено вчора"),
    ("10 августа 2026 г.", NOW, "10 августа 2026 г."),
    ("Сегодня в 16:33", NOW, "Сегодня в 16:33"),
    ("", NOW, ""),
    (None, NOW, None),
], ids=["time-kept-yesterday", "time-kept-today", "yesterday", "day-before-yesterday", "older-no-year",
        "other-year", "today", "kyiv-calendar", "prefix", "russian-month", "russian-text", "empty", "none"])
def test_format_published_date(text, now, result):
    assert format_published_date(text, now) == result
