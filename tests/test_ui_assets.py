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

    def test_theme_picker_contains_every_supported_palette(self):
        script = (ROOT / "bot/server/static/app.js").read_text(encoding="utf-8")
        for theme in ("midnight", "cinema", "ocean", "royal", "aurora", "amoled", "graphite", "light"):
            with self.subTest(theme=theme):
                self.assertIn(f"'{theme}'", script)
        self.assertIn("akmv-dark-theme", script)
        self.assertIn("picker.dataset.themePicker", script)


if __name__ == "__main__":
    unittest.main()
