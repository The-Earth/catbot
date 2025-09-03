import unittest
import catbot
import json


class Tester(unittest.TestCase):
    def test_bot_login(self):
        config = json.load(open('test.json'))
        self.bot = catbot.Bot(config)


if __name__ == '__main__':
    unittest.main()
