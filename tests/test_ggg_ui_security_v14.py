from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class GggUiSecurityTests(unittest.TestCase):
    def test_status_exposes_exact_local_redirect(self):
        app=(ROOT/"app.py").read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:{self.server.server_port}/oauth/callback",app)

    def test_oauth_error_is_html_escaped(self):
        app=(ROOT/"app.py").read_text(encoding="utf-8")
        self.assertIn("html_lib.escape(str(error))",app)
        self.assertIn("html_lib.escape(str(e))",app)

    def test_ui_shows_registered_redirect_uri(self):
        js=(ROOT/"web"/"app.js").read_text(encoding="utf-8")
        self.assertIn("Redirect URI que deve estar registrado",js)
        self.assertIn("127.0.0.1:8777/oauth/callback",js)

if __name__=="__main__":
    unittest.main()
