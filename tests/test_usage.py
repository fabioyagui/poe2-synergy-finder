"""lab usage (PoE 2): remoção de itens e de nós no XML do PoB, e leitura da busca do poe.ninja (sem rede)."""
import unittest

from src import ninja
from src.lab import usage
from tests.test_ninja_snapshots import _field, _ndic

XML = """<PathOfBuilding2>
<Build level="90" className="Mercenary" ascendClassName="Gemling Legionnaire"/>
<Tree activeSpec="1">
<Spec treeVersion="0_5" nodes="100,200,300" ascendClassId="3">
<Sockets><Socket nodeId="61834" itemId="3"/><Socket nodeId="1" itemId="0"/></Sockets>
</Spec>
<Spec treeVersion="0_5" nodes="100,999"/>
</Tree>
<Items>
<Item id="1">Rarity: UNIQUE
Ming's Heart
Amethyst Ring</Item>
<Item id="2">Rarity: RARE
Doom Grip
Ornate Gauntlets</Item>
<Item id="3">Rarity: MAGIC
Sapphire of the Thing
Sapphire</Item>
<ItemSet id="1">
<Slot itemPbURL="" name="Ring 1" itemId="1"/>
<Slot itemPbURL="" name="Gloves" itemId="2"/>
<Slot itemPbURL="" name="Weapon 1 Swap" itemId="1"/>
</ItemSet>
</Items>
</PathOfBuilding2>"""


class XmlTests(unittest.TestCase):
    def test_equipped_skips_empty_and_swap(self):
        got = [(k, w, i) for k, w, i, _t in usage.equipped(XML)]
        self.assertEqual(got, [("slot", "Ring 1", "1"), ("slot", "Gloves", "2"), ("socket", "61834", "3")])

    def test_labels_uniques_and_jewels_only(self):
        info = usage.items_of(XML)
        self.assertEqual(usage.label(*info["1"], "slot"), "Ming's Heart")
        self.assertIsNone(usage.label(*info["2"], "slot"))  # raro de slot fica de fora
        self.assertEqual(usage.label(*info["3"], "socket"), "Magic Jewel")

    def test_without_item_empties_one_slot(self):
        tag = next(t for k, w, i, t in usage.equipped(XML) if w == "Ring 1")
        out = usage.without(XML, tag, "1")
        self.assertIn('name="Ring 1" itemId="0"', out)
        self.assertIn('name="Weapon 1 Swap" itemId="1"', out)

    def test_without_node_touches_only_active_spec(self):
        self.assertEqual(usage.allocated(XML), ["100", "200", "300"])
        out = usage.without_node(XML, "200")
        self.assertEqual(usage.allocated(out), ["100", "300"])
        self.assertIn('nodes="100,999"', out)  # o segundo Spec não muda


class NinjaSearchTests(unittest.TestCase):
    def test_decode_search_reads_characters_and_names(self):
        dim = _field(1, b"class") + _field(2, b"class") + _field(3, _field(2, 7)) + _field(3, _field(1, 1) + _field(2, 3))
        cols = (_field(12, _field(1, b"account") + _field(2, b"account") + _field(7, b"acc-1") + _field(7, b"acc-2"))
                + _field(12, _field(1, b"name") + _field(2, b"name") + _field(7, b"Hero") + _field(7, b"Sidekick")))
        body = _field(1, _field(1, 10) + _field(2, dim) + _field(6, _field(1, b"class") + _field(2, b"h")) + cols)
        out = ninja.decode_search(body, names_for=lambda h: ["Gemling Legionnaire", "Spirit Walker"])
        self.assertEqual(out["total"], 10)
        self.assertEqual(out["dims"]["class"], [("Gemling Legionnaire", 7), ("Spirit Walker", 3)])
        self.assertEqual(out["characters"], [("acc-1", "Hero"), ("acc-2", "Sidekick")])
        self.assertEqual(ninja.usage(out["dims"], 10, "class", 1), [{"name": "Gemling Legionnaire", "pct": 70.0, "count": 7}])

    def test_pob_code_roundtrip(self):
        import base64
        import zlib
        code = base64.urlsafe_b64encode(zlib.compress(XML.encode())).decode().rstrip("=")
        self.assertEqual(ninja.pob_xml(code), XML)

    def test_dictionary_helper_is_shared(self):
        self.assertEqual(ninja.parse_dictionary(_ndic(["a", "bb"])), ["a", "bb"])


if __name__ == "__main__":
    unittest.main()
