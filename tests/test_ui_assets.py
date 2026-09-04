import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class UiAssetTests(unittest.TestCase):
    def test_templates_do_not_load_remote_scripts(self):
        for path in (ROOT / "bot/server/template").glob("*.html"):
            if path.name == "login.html":
                continue
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("<script src=\"http", text)
                self.assertNotIn("disable-devtool", text)


if __name__ == "__main__":
    unittest.main()
