import copy
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'editable-diagrams'
spec = importlib.util.spec_from_file_location('builder', SKILL / 'scripts' / 'build_diagram.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
NS = {'s': 'http://www.w3.org/2000/svg'}


class DiagramTests(unittest.TestCase):
    def setUp(self):
        self.scene = json.loads((SKILL / 'assets' / 'starter.json').read_text())

    def tree(self):
        return ET.fromstring(builder.render(self.scene))

    def test_stable_ids_when_renamed_or_resized(self):
        before = {e.get('id') for e in self.tree().iter() if e.get('id')}
        self.scene['nodes'][0]['label'] = 'Reference and concept'
        self.scene['card_width'] = 340
        after = {e.get('id') for e in self.tree().iter() if e.get('id')}
        self.assertEqual(before, after)

    def test_gutter_grows_for_long_label_and_keeps_anchors(self):
        old = float(self.tree().get('width'))
        self.scene['edges'][0]['label'] = 'A much longer connector label'
        self.scene['card_width'] = 330
        root = self.tree()
        self.assertGreater(float(root.get('width')), old)
        first = root.find("s:g[@id='visual-concept']", NS)
        second = root.find("s:g[@id='editable-artwork']", NS)
        x1 = float(first.get('transform').split('(')[1].split()[0])
        x2 = float(second.get('transform').split('(')[1].split()[0])
        self.assertGreaterEqual(x2 - x1 - 330, len(self.scene['edges'][0]['label']) * 10 + 32)
        edge = root.find("s:g[@id='concept-to-artwork']", NS)
        numbers = [float(n) for n in re.findall(r'[0-9.]+', edge.find("s:path[@data-part='shaft']", NS).get('d'))]
        self.assertEqual(numbers[0], x1 + 330 + 8)
        self.assertEqual(numbers[-1], x2 - 18)

    def test_transparent_canvas_and_opaque_cards(self):
        root = self.tree()
        self.assertIsNone(root.find("s:rect[@id='diagram-background']", NS))
        self.assertTrue(all(rect.get('fill') == '#ffffff' for rect in root.findall('s:g/s:rect', NS)))
        self.scene['background'] = '#ffeecc'
        self.assertEqual(self.tree().find("s:rect[@id='diagram-background']", NS).get('fill'), '#ffeecc')

    def test_text_is_escaped_and_remains_text(self):
        value = '<script>alert("hello")</script> & café'
        self.scene['nodes'][0]['label'] = value
        root = self.tree()
        self.assertFalse(root.findall('.//s:script', NS))
        self.assertEqual(root.find("s:g[@id='visual-concept']", NS).get('data-label'), value)
        self.assertTrue(root.findall('.//s:text', NS))

    def test_multiline_edge_labels_fit_canvas(self):
        self.scene['edges'][0]['label'] = '\n'.join(['A label'] * 20)
        root = self.tree()
        height = float(root.get('height'))
        labels = root.findall("s:g[@id='concept-to-artwork']/s:text", NS)
        self.assertEqual(len(labels), 20)
        self.assertLess(max(float(label.get('y')) for label in labels), height - 16)

    def test_content_growth_increases_height(self):
        original = float(self.tree().get('height'))
        self.scene['nodes'][0]['items'] = ['A long explanation about editable diagrams and maintaining useful spacing.'] * 8
        self.assertGreater(float(self.tree().get('height')), original)

    def test_invalid_graphs_and_ids_are_rejected(self):
        for mutate in [
            lambda s: s['nodes'][0].update(id='diagram'),
            lambda s: s['nodes'][1].update(id=s['nodes'][0]['id']),
            lambda s: s['edges'][0].update(to='missing'),
            lambda s: s['edges'][0].update(to='inspect-and-refine'),
            lambda s: s.update(gap=float('nan')),
        ]:
            with self.subTest(mutate=mutate):
                scene = copy.deepcopy(self.scene); mutate(scene)
                with self.assertRaises(ValueError): builder.render(scene)

    def test_single_node(self):
        self.scene['nodes'] = self.scene['nodes'][:1]; self.scene['edges'] = []
        self.assertGreater(float(self.tree().get('width')), 0)

    def test_example_is_reproducible_and_self_contained(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'workflow'
            svg = builder.build(self.scene, output)
            document = output.with_suffix('.html').read_text()
            self.assertIn(svg, document)
            self.assertNotIn('@@SVG@@', document)
            self.assertEqual(json.loads(output.with_suffix('.json').read_text()), self.scene)
            self.assertEqual(svg, (ROOT / 'examples/editable-diagrams/workflow.svg').read_text())
            self.assertEqual(document, (ROOT / 'examples/editable-diagrams/workflow.html').read_text())


if __name__ == '__main__':
    unittest.main()
