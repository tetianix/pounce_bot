import pytest

from scrapers.olx import clean_price


def expected(price, currency="UAH", converted=False, label=None):
    return {"price": price, "currency": currency, "converted": converted, "label": label}


@pytest.mark.parametrize("text, result", [
    ("1 500 грн.", expected(1500)),
    ("20000 грн.", expected(20000)),
    ("22 458.27 грн.", expected(22458, converted=True)),
    ("22 458,27 грн.", expected(22458, converted=True)),
    ("997 102.05 грн.", expected(997102, converted=True)),
    ("500 $", expected(500, currency="USD")),
    ("450 €", expected(450, currency="EUR")),
    ("12 500 $", expected(12500, currency="USD")),
    ("29 195.74 грн.Договірна", expected(29195, converted=True, label="Договірна")),
    ("8 000 грн.Договірна", expected(8000, label="Договірна")),
    ("Безкоштовно", expected(None, label="Безкоштовно")),
    ("Обмін", expected(None, label="Обмін")),
    ("1 500 грн.", expected(1500)),
    ("", expected(None)),
], ids=["uah", "uah-no-spaces", "converted-dot", "converted-comma", "converted-large", "usd", "eur",
        "usd-thousands", "negotiable-converted", "negotiable-uah", "free", "exchange",
        "non-breaking-spaces", "empty"])
def test_clean_price(text, result):
    assert clean_price(text) == result
