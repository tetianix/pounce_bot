import os
import unittest
from pathlib import Path

BOT = {}


def setUpModule():
    os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKENtesttokenTESTTOKENtesttoken")
    path = Path(__file__).resolve().parent.parent / "bot.py"
    source = path.read_text(encoding="utf-8").replace("asyncio.run(main())", "")
    exec(compile(source, str(path), "exec"), BOT)


class FormatPriceRangeTest(unittest.TestCase):
    def test_both(self):
        self.assertEqual(BOT["format_price_range"](300, 700), "300–700 грн")

    def test_only_min(self):
        self.assertEqual(BOT["format_price_range"](1500, None), "від 1500 грн")

    def test_only_max(self):
        self.assertEqual(BOT["format_price_range"](None, 300), "до 300 грн")

    def test_none(self):
        self.assertEqual(BOT["format_price_range"](None, None), "будь-яка")

    def test_zero_from_watches_table_means_no_limit(self):
        self.assertEqual(BOT["format_price_range"](0, 0), "будь-яка")
        self.assertEqual(BOT["format_price_range"](0, 700), "до 700 грн")


class FormatMoneyTest(unittest.TestCase):
    def test_uah_with_thousands(self):
        self.assertEqual(BOT["format_money"](22458, "UAH"), "22 458 грн")

    def test_small(self):
        self.assertEqual(BOT["format_money"](300, "UAH"), "300 грн")

    def test_converted(self):
        self.assertEqual(BOT["format_money"](22458, "UAH", True), "≈ 22 458 грн")

    def test_usd(self):
        self.assertEqual(BOT["format_money"](500, "USD"), "500 $")

    def test_eur(self):
        self.assertEqual(BOT["format_money"](450, "EUR"), "450 €")

    def test_unknown_currency_falls_back_to_uah(self):
        self.assertEqual(BOT["format_money"](100, None), "100 грн")


class IsRealChangeTest(unittest.TestCase):
    def test_uah_any_change(self):
        self.assertTrue(BOT["is_real_change"](1500, 1490, False))

    def test_uah_same(self):
        self.assertFalse(BOT["is_real_change"](1500, 1500, False))

    def test_converted_small_change_ignored(self):
        self.assertFalse(BOT["is_real_change"](10000, 10300, True))
        self.assertFalse(BOT["is_real_change"](10000, 9700, True))

    def test_converted_big_change_counts(self):
        self.assertTrue(BOT["is_real_change"](10000, 10301, True))
        self.assertTrue(BOT["is_real_change"](10000, 9000, True))


if __name__ == "__main__":
    unittest.main()
