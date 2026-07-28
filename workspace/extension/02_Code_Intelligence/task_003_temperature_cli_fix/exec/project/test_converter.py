import unittest

from converter import celsius_to_fahrenheit


class ConverterTests(unittest.TestCase):
    def test_freezing_point(self):
        self.assertAlmostEqual(celsius_to_fahrenheit(0), 32.0)

    def test_boiling_point(self):
        self.assertAlmostEqual(celsius_to_fahrenheit(100), 212.0)

    def test_same_value(self):
        self.assertAlmostEqual(celsius_to_fahrenheit(-40), -40.0)


if __name__ == "__main__":
    unittest.main()
