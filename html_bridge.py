"""Turns index.html into live Solara components.

index.html keeps the page structure and style.css keeps the look. This module parses the HTML
into a small tree and rebuilds each element as a Solara component, so that buttons, sliders and
sections become real Python callbacks while keeping their original ids and classes (the CSS
selectors in style.css therefore still apply).
"""
import html as _html
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional

import solara

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SKIP_TAGS = {"script", "style", "link", "meta", "title", "head"}


class Node:
    def __init__(self, tag: str, attrs=None, text: Optional[str] = None):
        self.tag = tag
        self.attrs = {k: (v or "") for k, v in (attrs or [])}
        self.children: List["Node"] = []
        self.text = text

    @property
    def id(self) -> Optional[str]:
        return self.attrs.get("id")

    @property
    def classes(self) -> List[str]:
        return self.attrs.get("class", "").split()

    def text_content(self) -> str:
        if self.tag == "#text":
            return self.text
        return "".join(c.text_content() for c in self.children)

    def has_descendant(self, pred) -> bool:
        return any(pred(c) or c.has_descendant(pred) for c in self.children)


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if self.stack[-1].tag not in ("script", "style"):
            self.stack[-1].children.append(Node("#text", text=data))


def to_html(node: Node) -> str:
    """Serialise a node back to HTML (used for leaves whose contents are plain markup)."""
    if node.tag == "#text":
        return _html.escape(node.text, quote=False)
    attrs = "".join(f' {k}="{_html.escape(v, quote=True)}"' for k, v in node.attrs.items())
    if node.tag in VOID:
        return f"<{node.tag}{attrs}>"
    inner = "".join(to_html(c) for c in node.children)
    return f"<{node.tag}{attrs}>{inner}</{node.tag}>"


def find(node: Node, pred) -> Optional[Node]:
    if pred(node):
        return node
    for c in node.children:
        found = find(c, pred)
        if found is not None:
            return found
    return None


@dataclass
class Slot:
    """Dynamic content for an element with a given id.
    html: replaces the element's inner HTML (leaf elements)
    children: replaces its children with Solara components
    attrs: extra or overriding attributes (style, class, ...)"""
    html: Optional[str] = None
    children: Optional[list] = None
    attrs: Dict[str, str] = field(default_factory=dict)


class Template:
    """A parsed index.html. render(hooks) returns the Solara components for <body>."""

    def __init__(self, path: Path):
        builder = _TreeBuilder()
        builder.feed(Path(path).read_text(encoding="utf-8"))
        self.body = find(builder.root, lambda n: n.tag == "body")

    def render(self, hooks) -> list:
        out = []
        for child in self.body.children:
            comp = self._component(child, hooks, None)
            if comp is not None:
                out.append(comp)
        return out

    def _component(self, node: Node, hooks, parent_id):
        if node.tag == "#text":
            text = node.text.strip()
            return solara.HTML("span", unsafe_innerHTML=_html.escape(text, quote=False)) if text else None
        if node.tag in SKIP_TAGS or hooks.skip(node):
            return None
        if not hooks.visible(node):
            return None
        replaced = hooks.replace(node)
        if replaced is not None:
            return replaced
        if node.tag == "button":
            return hooks.button(node, parent_id)
        if node.tag == "input":
            return hooks.widget(node)

        slot = hooks.slot(node)
        attrs = {k: v for k, v in node.attrs.items() if k != "hidden"}
        if slot is not None and slot.attrs:
            attrs.update(slot.attrs)
        if slot is not None and slot.children is not None:
            return solara.v.Html(tag=node.tag, attributes=attrs, children=slot.children)
        if slot is not None and slot.html is not None:
            return solara.HTML(tag=node.tag, unsafe_innerHTML=slot.html, attributes=attrs)
        # A container must be rebuilt element by element if anything inside it is live
        # (a button, a slider, or an element whose content is filled in by Python).
        if node.has_descendant(hooks.is_live):
            kids = [self._component(c, hooks, node.id) for c in node.children]
            return solara.v.Html(tag=node.tag, attributes=attrs, children=[k for k in kids if k is not None])
        inner = "".join(to_html(c) for c in node.children)
        return solara.HTML(tag=node.tag, unsafe_innerHTML=inner, attributes=attrs)
