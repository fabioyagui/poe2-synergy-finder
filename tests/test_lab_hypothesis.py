"""Hipótese de patch: validação pura sempre; a prova no PoB 2 headless só com o motor configurado.

Prova exigida: voltar uma gem a um valor antigo conhecido (cooldown) muda o DPS na direção esperada, e o reset
devolve o número exato do PoB.
"""
import tempfile
import unittest
from pathlib import Path

from src.lab import hypothesis
from tests.test_lab import POB_SKIP


class PureTests(unittest.TestCase):
    def tearDown(self):
        hypothesis.set_active(None)

    def test_normalize_validates_fields(self):
        out = hypothesis.normalize({"nome": "x", "gems": [{"skill": "FallingThunderPlayer", "set": {"cooldown": 2}}], "mods": [" 20% more Damage "]})
        self.assertEqual(out["gems"][0]["set"], {"cooldown": 2})
        self.assertEqual(out["mods"], ["20% more Damage"])
        with self.assertRaises(ValueError):
            hypothesis.normalize({"gems": [{"skill": "X", "set": {"manaMultiplier": 1}}]})
        with self.assertRaises(ValueError):
            hypothesis.normalize({"gems": [{"skill": "X", "scale": {"stat": "1"}}]})
        with self.assertRaises(ValueError):
            hypothesis.normalize({"gems": [{"skill": "X", "statSet": 0}]})
        with self.assertRaises(ValueError):
            hypothesis.normalize({"gems": [{"set": {"cooldown": 1}}]})
        with self.assertRaises(ValueError):
            hypothesis.normalize({})

    def test_label_stamp_and_mods_follow_the_active_hypothesis(self):
        self.assertIsNone(hypothesis.label())
        self.assertEqual(hypothesis.stamp(), "")
        self.assertEqual(hypothesis.custom_mods(), "")
        hypothesis.set_active(hypothesis.normalize({"nome": "n", "fonte": "notas", "mods": ["a", "b"]}))
        self.assertEqual(hypothesis.label()["mods"], 2)
        self.assertTrue(hypothesis.stamp().startswith("hip "))
        self.assertEqual(hypothesis.custom_mods(), "a\nb")

    def test_install_extension_hooks_the_bridge_copy(self):
        with tempfile.TemporaryDirectory() as td:
            api = Path(td) / "API"
            api.mkdir()
            (api / "Handlers.lua").write_text('local handlers = {}\nrequire("API.SynergyTree").install(handlers)\n'
                                              'require("API.SynergyWorkbench").install(handlers)\n', encoding="utf-8")
            hypothesis.install_extension(Path(td))
            hypothesis.install_extension(Path(td))  # idempotente
            text = (api / "Handlers.lua").read_text(encoding="utf-8")
            self.assertEqual(text.count('require("API.SynergyHypothesis").install(handlers)'), 1)
            self.assertTrue((api / "SynergyHypothesis.lua").exists())


@unittest.skipIf(POB_SKIP, POB_SKIP)
class RealHypothesisTests(unittest.TestCase):
    """Monk 14, Tempest Bell: cooldown antigo de 1 s limita a velocidade (PoB 2 capa Speed em 1/cooldown)."""

    @classmethod
    def tearDownClass(cls):
        from src.lab import service
        service.handle("hypothesis", {"reset": True})
        service.handle("close", {})

    def test_old_cooldown_lowers_dps_and_reset_restores_exact_numbers(self):
        from src.lab import service
        service.handle("open", {"from": "new", "class": "Monk", "level": 14, "weapon": "Gothic Quarterstaff", "name": "hipotese"})
        service.handle("add_skill", {"gems": [["Tempest Bell", 5]]})
        base = service.handle("select", {"group": 1})["stats"]
        self.assertNotIn("hipotese", base)

        with self.assertRaises(ValueError):
            service.handle("hypothesis", {"mods": ["blablabla xyz"]})
        self.assertIsNone(service.handle("hypothesis", {})["ativa"])

        out = service.handle("hypothesis", {"nome": "cooldown antigo", "gems": [{"skill": "Tempest Bell", "set": {"cooldown": 1.0, "manaCost": 99}}],
                                            "mods": ["20% more Damage"]})
        self.assertEqual(out["hipotese"]["nome"], "cooldown antigo")
        self.assertEqual(out["gems"][0]["id"], "TempestBellPlayer")
        self.assertEqual(out["gems"][0]["depois"]["cooldown"], 1.0)
        hyp = out["stats"]
        self.assertLess(hyp["TotalDPS"], base["TotalDPS"])
        self.assertLess(hyp["Speed"], base["Speed"])
        self.assertEqual(hyp["ManaCost"], 99)
        self.assertIn("hipotese", service.handle("stats", {}))

        back = service.handle("hypothesis", {"reset": True})
        self.assertIsNone(back["ativa"])
        self.assertNotIn("hipotese", back)
        for key in ("TotalDPS", "Speed", "ManaCost", "CritChance", "Life"):
            self.assertEqual(back["stats"][key], base[key], key)


if __name__ == "__main__":
    unittest.main()
