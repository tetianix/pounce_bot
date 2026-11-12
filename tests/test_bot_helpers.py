import pytest


@pytest.mark.parametrize("min_price, max_price, text", [
    (300, 700, "300–700 грн"),
    (1500, None, "від 1 500 грн"),
    (1500, 30000, "1 500–30 000 грн"),
    (None, 300, "до 300 грн"),
    (None, 12000, "до 12 000 грн"),
    (None, None, "будь-яка"),
    (0, 0, "будь-яка"),
    (0, 700, "до 700 грн"),
], ids=["both", "only-min", "both-thousands", "only-max", "only-max-thousands", "none",
        "zero-means-no-limit", "zero-min-with-max"])
def test_format_price_range(app, min_price, max_price, text):
    assert app["format_price_range"](min_price, max_price) == text


@pytest.mark.parametrize("args, text", [
    ((22458, "UAH"), "22 458 грн"),
    ((300, "UAH"), "300 грн"),
    ((22458, "UAH", True), "≈ 22 458 грн"),
    ((500, "USD"), "500 $"),
    ((450, "EUR"), "450 €"),
    ((100, None), "100 грн"),
], ids=["uah-thousands", "small", "converted", "usd", "eur", "unknown-currency-is-uah"])
def test_format_money(app, args, text):
    assert app["format_money"](*args) == text


@pytest.mark.parametrize("old, new, converted, real", [
    (1500, 1490, False, True),
    (1500, 1500, False, False),
    (10000, 10300, True, False),
    (10000, 9700, True, False),
    (10000, 10301, True, True),
    (10000, 9000, True, True),
], ids=["uah-any-change", "uah-same", "converted-small-up", "converted-small-down",
        "converted-big-up", "converted-big-down"])
def test_is_real_change(app, old, new, converted, real):
    assert app["is_real_change"](old, new, converted) is real


@pytest.mark.parametrize("args, text", [
    ((2200, 2000, "UAH"), "📉 Подешевшало: 2 200 → 2 000 грн"),
    ((2000, 2500, "UAH"), "📈 Подорожчало: 2 000 → 2 500 грн"),
    ((500, 450, "USD"), "📉 Подешевшало: 500 → 450 $"),
    ((22458, 20000, "UAH", True), "📉 Подешевшало: ≈ 22 458 → 20 000 грн"),
], ids=["cheaper", "more-expensive", "usd", "converted"])
def test_format_price_change(app, args, text):
    assert app["format_price_change"](*args) == text
