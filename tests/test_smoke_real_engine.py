"""Smoke test contra o Motor PoB real instalado nesta máquina.

Diferente do resto da suíte, não usa fixtures: sobe o LuaJIT + PoB headless
configurados em data/pob/engine_config.json e carrega uma build real. É pulado
quando o motor não está pronto ou não há build importada.
"""
import unittest

from src import pob_engine

BUILD_XML = pob_engine.PROJECT_ROOT / "data" / "pob" / "current.xml"


def _skip_reason() -> str:
    if not BUILD_XML.exists():
        return "sem build importada em data/pob/current.xml"
    try:
        if not pob_engine.setup_status()["ready"]:
            return "Motor PoB não configurado nesta máquina"
    except Exception as exc:
        return f"diagnóstico do motor falhou: {exc}"
    return ""


SKIP = _skip_reason()


@unittest.skipIf(SKIP, SKIP)
class RealEngineSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = pob_engine.EngineClient()
        try:
            cls.engine.start()
            cls.engine.load_xml(BUILD_XML.read_text(encoding="utf-8"), "smoke test")
            cls.snapshot = cls.engine.calculate_snapshot()
        except Exception:
            cls.engine.stop(force=True)
            raise

    @classmethod
    def tearDownClass(cls):
        cls.engine.stop()

    def test_engine_answers_ping_after_loading_build(self):
        self.assertTrue(self.engine.request("ping", {}, timeout=8).get("ok"))

    def test_stats_are_numeric_and_not_empty(self):
        stats = self.snapshot["stats"]
        numeric = [v for v in stats.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        self.assertGreater(len(numeric), 10, f"stats retornados: {sorted(stats)[:20]}")
        self.assertGreater(stats.get("Life", 0), 0)

    def test_build_has_skills_and_allocated_tree(self):
        self.assertTrue(self.snapshot["skills"])
        self.assertTrue(self.snapshot["tree"])


if __name__ == "__main__":
    unittest.main()
