import unittest

from scrapers.olx import clean_price


class CleanPriceTest(unittest.TestCase):
    def check(self, text, price, currency="UAH", converted=False, label=None):
        self.assertEqual(clean_price(text), {
            "price": price, "currency": currency, "converted": converted, "label": label,
        })

    def test_uah_whole(self):
        self.check("1 500 грн.", 1500)

    def test_uah_without_spaces(self):
        self.check("20000 грн.", 20000)

    def test_converted_from_currency_drops_kopecks(self):
        self.check("22 458.27 грн.", 22458, converted=True)

    def test_converted_with_comma(self):
        self.check("22 458,27 грн.", 22458, converted=True)

    def test_converted_large(self):
        self.check("997 102.05 грн.", 997102, converted=True)

    def test_usd(self):
        self.check("500 $", 500, currency="USD")

    def test_eur(self):
        self.check("450 €", 450, currency="EUR")

    def test_usd_thousands(self):
        self.check("12 500 $", 12500, currency="USD")

    def test_negotiable_keeps_price(self):
        self.check("29 195.74 грн.Договірна", 29195, converted=True, label="Договірна")

    def test_negotiable_uah(self):
        self.check("8 000 грн.Договірна", 8000, label="Договірна")

    def test_free(self):
        self.check("Безкоштовно", None, label="Безкоштовно")

    def test_exchange(self):
        self.check("Обмін", None, label="Обмін")

    def test_non_breaking_spaces(self):
        self.check("1 500 грн.", 1500)

    def test_empty(self):
        self.check("", None)


if __name__ == "__main__":
    unittest.main()
