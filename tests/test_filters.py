import pytest

from filters import filter_exact


def ads(*names):
    return [{"name": name} for name in names]


def names(result):
    return [ad["name"] for ad in result]


@pytest.mark.parametrize("titles, query, kept", [
    (("Apple iPhone 13 Pro", "13 айфон iPhone", "iPhone 12"), "iphone 13",
     ["Apple iPhone 13 Pro", "13 айфон iPhone"]),
    (("iPhone 130", "iPhone13", "iPhone 13, чохол"), "iphone 13", ["iPhone 13, чохол"]),
    (("Помада Dior Rouge", "Помади Dior", "Туш Dior"), "помада dior", ["Помада Dior Rouge"]),
], ids=["ignores-case-and-order", "whole-words-only", "cyrillic"])
def test_keeps_titles_with_all_query_words(titles, query, kept):
    assert names(filter_exact(ads(*titles), query)) == kept


def test_query_without_words_keeps_everything():
    assert len(filter_exact(ads("a", "b"), "!!!")) == 2
