"""Real Pillow renderer regression without cloud login or robot I/O."""
import ast
from pathlib import Path
import tempfile
import unittest
from PIL import Image, ImageDraw


class RenderDependencyTest(unittest.TestCase):
    def test_actual_saved_map_renderer_palette_and_dimensions(self):
        source=Path(__file__).resolve().parents[1]/'xiaomi_x10_map.py'
        tree=ast.parse(source.read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='XiaomiX10MapClient')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='render_single_map_to_png')
        ns={'Image':Image,'ImageDraw':ImageDraw}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'<actual saved map renderer>','exec'),ns)
        class Fixture:
            def _header_from_raw(self, raw):
                return {'width':2,'height':2,'left':0,'top':0,'grid_size':50}
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'map.png'
            ns['render_single_map_to_png'](Fixture(),bytes(27)+bytes([0,1,2,128]),target)
            with Image.open(target) as image:
                self.assertEqual(image.size,(8,8))
                self.assertEqual(image.mode,'RGBA')
                self.assertEqual(image.getpixel((0,0)),(13,16,23,255))
                self.assertEqual(image.getpixel((7,7)),(43,48,61,255))


if __name__=='__main__':unittest.main()
