import unittest

from filters import filter_exact


def ads(*names):
    return [{"name": name} for name in names]


def names(result):
    return [ad["name"] for ad in result]


class FilterExactTest(unittest.TestCase):
    def test_keeps_titles_with_all_words_ignoring_case_and_order(self):
        result = filter_exact(ads("Apple iPhone 13 Pro", "13 айфон iPhone", "iPhone 12"), "iphone 13")
        self.assertEqual(names(result), ["Apple iPhone 13 Pro", "13 айфон iPhone"])

    def test_word_must_match_whole_not_part(self):
        result = filter_exact(ads("iPhone 130", "iPhone13", "iPhone 13, чохол"), "iphone 13")
        self.assertEqual(names(result), ["iPhone 13, чохол"])

    def test_cyrillic_words(self):
        result = filter_exact(ads("Помада Dior Rouge", "Помади Dior", "Туш Dior"), "помада dior")
        self.assertEqual(names(result), ["Помада Dior Rouge"])

    def test_query_without_words_keeps_everything(self):
        self.assertEqual(len(filter_exact(ads("a", "b"), "!!!")), 2)


if __name__ == "__main__":
    unittest.main()
