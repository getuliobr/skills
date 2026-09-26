#!/usr/bin/env python3
"""Build a simple horizontal pipeline. Python standard library only."""
import argparse
import html
import json
import math
from pathlib import Path
import re
import textwrap
import xml.etree.ElementTree as ET

ASSETS = Path(__file__).resolve().parent.parent / 'assets'
ID = re.compile(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z')
COLOR = re.compile(r'#[0-9a-fA-F]{6}\Z')


def number(scene, name, default, minimum):
    value = scene.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f'{name} must be a finite number >= {minimum}')
    return float(value)


def wrapped(value, width, size):
    # Conservative advance estimate. Always visually inspect the chosen font.
    limit = max(1, int(width / (size * .68)))
    return [line for paragraph in str(value).split('\n') for line in (textwrap.wrap(paragraph, limit) or [''])]


def render(scene):
    nodes, edges = scene.get('nodes', []), scene.get('edges', [])
    if not nodes:
        raise ValueError('At least one node is required')
    reserved = {'diagram', 'diagram-title', 'diagram-description', 'diagram-decisions', 'diagram-background', 'visible-title'}
    ids = set(reserved)
    for entry in nodes + edges:
        key = entry.get('id', '')
        if not ID.fullmatch(key) or key in ids:
            raise ValueError(f'Invalid or duplicate semantic ID: {key!r}')
        ids.add(key)
        if not isinstance(entry.get('label'), str) or not entry['label'].strip():
            raise ValueError(f'{key} needs a readable label')
    width = number(scene, 'card_width', 280, 180)
    requested_gap = number(scene, 'gap', 110, 40)
    padding = number(scene, 'padding', 32, 16)
    background = scene.get('background', 'transparent')
    if background != 'transparent' and not COLOR.fullmatch(background):
        raise ValueError('background must be transparent or a six-digit hex color')
    positions = {node['id']: i for i, node in enumerate(nodes)}
    gaps = [requested_gap] * (len(nodes) - 1)
    used_pairs = set()
    for edge in edges:
        source, target = edge.get('from'), edge.get('to')
        if source not in positions or target not in positions or positions[target] != positions[source] + 1:
            raise ValueError('Starter supports forward edges between adjacent nodes only; use a tailored layout for other graphs')
        if (source, target) in used_pairs:
            raise ValueError('Starter supports one edge per adjacent pair')
        used_pairs.add((source, target))
        longest = max(len(line) for line in edge['label'].split('\n'))
        gaps[positions[source]] = max(requested_gap, longest * 10 + 32)
    text_layout = []
    for node in nodes:
        if not COLOR.fullmatch(node.get('color', '#2563eb')):
            raise ValueError(f"Invalid color for {node['id']}")
        if not isinstance(node.get('items', []), list) or not all(isinstance(item, str) for item in node.get('items', [])):
            raise ValueError('Node items must be a list of strings')
        headings = wrapped(node['label'], width - 44, 20)
        items = [wrapped(item, width - 62, 16) for item in node.get('items', [])]
        height = 26 + len(headings) * 27 + 18 + sum(len(lines) * 23 + 12 for lines in items) + 16
        text_layout.append((headings, items, height))
    card_height = max(180, *(entry[2] for entry in text_layout))
    heading_lines = wrapped(scene.get('title', 'Editable diagram'), len(nodes) * width + sum(gaps), 25) if scene.get('show_title', False) else []
    top = padding + (len(heading_lines) * 32 + 20 if heading_lines else 0)
    canvas_width = padding * 2 + len(nodes) * width + sum(gaps)
    longest_edge = max((len(edge['label'].split('\n')) for edge in edges), default=0)
    canvas_height = top + max(card_height, card_height / 2 + 30 + longest_edge * 21) + padding
    e = lambda value: html.escape(str(value), quote=True)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" id="diagram" width="{canvas_width:g}" height="{canvas_height:g}" viewBox="0 0 {canvas_width:g} {canvas_height:g}" role="img" aria-labelledby="diagram-title diagram-description" font-family="Arial, Helvetica, sans-serif">',
             f'<title id="diagram-title">{e(scene.get("title", "Editable diagram"))}</title>',
             '<desc id="diagram-description">Editable horizontal process diagram. Named groups identify stages and connections.</desc>',
             f'<metadata id="diagram-decisions">{e(json.dumps(scene.get("decisions", []), ensure_ascii=False))}</metadata>']
    if background != 'transparent':
        parts.append(f'<rect id="diagram-background" width="100%" height="100%" fill="{background}"/>')
    if heading_lines:
        parts.append('<g id="visible-title" data-label="Diagram heading" fill="#182338" font-size="25" font-weight="700">')
        for i, line in enumerate(heading_lines):
            parts.append(f'<text x="{padding:g}" y="{padding + 25 + i * 32:g}">{e(line)}</text>')
        parts.append('</g>')
    xs = []; x = padding
    for i, (node, (headings, items, _)) in enumerate(zip(nodes, text_layout)):
        xs.append(x); color = node.get('color', '#2563eb')
        parts.append(f'<g id="{node["id"]}" data-label="{e(node["label"])}" transform="translate({x:g} {top:g})">')
        parts.append(f'<rect width="{width:g}" height="{card_height:g}" rx="14" fill="#ffffff" stroke="{color}" stroke-width="1.5"/>')
        parts.append(f'<path d="M20 14 H{width-20:g}" fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round"/>')
        y = 48
        for line in headings:
            parts.append(f'<text data-part="heading" x="22" y="{y:g}" fill="{color}" font-size="20" font-weight="700">{e(line)}</text>'); y += 27
        y += 15
        for lines in items:
            parts.append(f'<circle cx="25" cy="{y-5:g}" r="2.5" fill="{color}"/>')
            for line in lines:
                parts.append(f'<text data-part="body" x="38" y="{y:g}" fill="#40516a" font-size="16">{e(line)}</text>'); y += 23
            y += 12
        parts.append('</g>')
        x += width + (gaps[i] if i < len(gaps) else 0)
    for edge in edges:
        i = positions[edge['from']]
        x1, x2, y = xs[i] + width + 8, xs[i+1] - 8, top + card_height / 2
        color = nodes[i].get('color', '#2563eb')
        parts.append(f'<g id="{edge["id"]}" data-label="{e(edge["label"])}" data-from="{edge["from"]}" data-to="{edge["to"]}" fill="{color}">')
        parts.append(f'<path data-part="shaft" d="M{x1:g} {y:g} H{x2-10:g}" fill="none" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<path data-part="arrowhead" d="M{x2:g} {y:g} l-12 -7 v14 Z"/>')
        for row, line in enumerate(edge['label'].split('\n')):
            parts.append(f'<text data-part="label" x="{(x1+x2)/2:g}" y="{y+30+row*21:g}" text-anchor="middle" font-size="15" font-weight="700">{e(line)}</text>')
        parts.append('</g>')
    parts.append('</svg>')
    svg = '\n'.join(parts)
    ET.fromstring(svg)
    return svg


def build(scene, output):
    svg = render(scene)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    template = (ASSETS / 'viewer.html').read_text(encoding='utf-8')
    # Substitute original template slots once; never rescan user content.
    slots = {'TITLE': html.escape(scene.get('title', 'Editable diagram')), 'SVG': svg}
    document = re.sub(r'@@(TITLE|SVG)@@', lambda match: slots[match.group(1)], template)
    outputs = {'.svg': svg, '.html': document, '.json': json.dumps(scene, indent=2, ensure_ascii=False) + '\n'}
    for suffix, content in outputs.items():
        Path(str(output) + suffix).write_text(content, encoding='utf-8')
    return svg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene', type=Path)
    parser.add_argument('--output', required=True, type=Path, help='Output basename, without extension')
    args = parser.parse_args()
    try:
        build(json.loads(args.scene.read_text(encoding='utf-8')), args.output)
    except (ValueError, OSError, TypeError) as error:
        parser.exit(2, f'Error: {error}\n')
    print(f'Created {args.output}.html, .svg, and .json')


if __name__ == '__main__':
    main()
