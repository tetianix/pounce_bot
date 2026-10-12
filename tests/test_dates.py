import unittest
from datetime import date, datetime, timezone

from scrapers.olx import fix_date, parse_published_date


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class FixDateTest(unittest.TestCase):
    def test_today_moves_three_hours_in_summer_time(self):
        self.assertEqual(fix_date("Сьогодні о 08:56", utc(2026, 10, 11, 9, 14)), "Сьогодні о 11:56")

    def test_yesterday(self):
        self.assertEqual(fix_date("Вчора о 12:00", utc(2026, 10, 11, 9, 14)), "Вчора о 15:00")

    def test_winter_time_is_two_hours(self):
        self.assertEqual(fix_date("Сьогодні о 08:56", utc(2026, 11, 15, 9, 0)), "Сьогодні о 10:56")

    def test_after_midnight_in_kyiv_stays_today(self):
        self.assertEqual(fix_date("Сьогодні о 22:30", utc(2026, 10, 11, 22, 40)), "Сьогодні о 01:30")

    def test_before_midnight_in_kyiv_becomes_yesterday(self):
        self.assertEqual(fix_date("Сьогодні о 20:30", utc(2026, 10, 11, 22, 40)), "Вчора о 23:30")

    def test_utc_yesterday_becomes_kyiv_today(self):
        self.assertEqual(fix_date("Вчора о 22:30", utc(2026, 10, 11, 5, 0)), "Сьогодні о 01:30")

    def test_two_days_ago_in_kyiv_becomes_full_date(self):
        self.assertEqual(fix_date("Вчора о 08:00", utc(2026, 10, 11, 22, 30)), "10 жовтня 2026 р.")

    def test_keeps_prefix_and_lowercase(self):
        self.assertEqual(fix_date("Оновлено сьогодні о 08:56", utc(2026, 10, 11, 9, 14)),
                         "Оновлено сьогодні о 11:56")

    def test_full_date_unchanged(self):
        self.assertEqual(fix_date("09 жовтня 2026 р.", utc(2026, 10, 11, 9, 14)), "09 жовтня 2026 р.")


class ParsePublishedDateTest(unittest.TestCase):
    now = utc(2026, 10, 11, 9, 0)

    def test_today(self):
        self.assertEqual(parse_published_date("Сьогодні о 11:56", self.now), date(2026, 10, 11))

    def test_yesterday(self):
        self.assertEqual(parse_published_date("Вчора о 23:30", self.now), date(2026, 10, 10))

    def test_with_prefix(self):
        self.assertEqual(parse_published_date("Оновлено сьогодні о 11:56", self.now), date(2026, 10, 11))

    def test_today_uses_kyiv_calendar(self):
        self.assertEqual(parse_published_date("Сьогодні о 01:30", utc(2026, 10, 11, 22, 40)), date(2026, 10, 12))

    def test_full_date(self):
        self.assertEqual(parse_published_date("09 жовтня 2026 р.", self.now), date(2026, 10, 9))

    def test_full_date_single_digit_day(self):
        self.assertEqual(parse_published_date("3 березня 2026 р.", self.now), date(2026, 3, 3))

    def test_unknown_month(self):
        self.assertIsNone(parse_published_date("09 октября 2026 г.", self.now))

    def test_impossible_date(self):
        self.assertIsNone(parse_published_date("31 лютого 2026 р.", self.now))

    def test_empty(self):
        self.assertIsNone(parse_published_date("", self.now))
        self.assertIsNone(parse_published_date(None, self.now))


if __name__ == "__main__":
    unittest.main()
