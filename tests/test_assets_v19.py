import unittest
from src import assets

class AssetsV19Tests(unittest.TestCase):
    def test_base_item_index_and_image_url(self):
        data={
            'Metadata/Items/Test':{
                'name':'Rattling Sceptre','release_state':'released','item_class':'Sceptre',
                'inventory_width':1,'inventory_height':3,
                'visual_identity':{'dds_file':'Art/2DItems/Weapons/Test.dds'}
            }
        }
        idx=assets._index(data)
        self.assertEqual(idx['rattling sceptre']['height'],3)
        self.assertEqual(assets.image_url(idx['rattling sceptre']['dds']),
                         'https://image.ggpk.exposed/poe2/Art/2DItems/Weapons/Test.dds?format=png')

    def test_rejects_non_art_path(self):
        self.assertEqual(assets.image_url('https://example.com/a.dds'),'')

if __name__=='__main__':unittest.main()
