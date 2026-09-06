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

    def test_mobile_navigation_and_broken_sponsor_cleanup_are_present(self):
        script = (ROOT / "bot/server/static/app.js").read_text(encoding="utf-8")
        stylesheet = (ROOT / "bot/server/static/app.css").read_text(encoding="utf-8")
        video = (ROOT / "bot/server/template/video.html").read_text(encoding="utf-8")
        self.assertIn("mobile-nav-toggle", script)
        self.assertIn("data-sponsor-image", script)
        self.assertIn("data-sponsor-ad", script)
        self.assertIn("NativeDownloadControl", video)
        self.assertIn(".nav-actions.mobile-open", stylesheet)
        self.assertIn("akmovieverse-vlc-playlist.m3u", video)

    def test_templates_use_local_versioned_frontend_assets(self):
        from bot.server.render_template import _finish_page
        html = _finish_page('<link rel="stylesheet" href="/static/app.css"><script src="/static/app.js"></script>', "midnight", False, "")
        self.assertIn('/static/app.css?v=3.1.2', html)
        self.assertIn('/static/app.js?v=3.1.2', html)


if __name__ == "__main__":
    unittest.main()
