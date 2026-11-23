"""A very small HTML tree: enough to read a page's source the same way in every browser,
without asking the browser to run anything."""
import re
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
UNSEEN = ("script", "style", "template", "noscript")


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.children, self.parent = tag, attrs or {}, [], parent

    def get(self, name):
        return self.attrs.get(name) or ""

    def has(self, name, word):
        """True if the space-separated attribute `name` (class, itemprop, rel ...) contains `word`."""
        return word in self.get(name).split()

    def walk(self):
        """Every element below this one, in document order."""
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.walk()

    def find_all(self, test):
        return [n for n in self.walk() if test(n)]

    def find(self, test):
        return next((n for n in self.walk() if test(n)), None)

    def text(self, skip=()):
        """The visible text below this element as one line, leaving out the tags in `skip`."""
        parts = []

        def collect(node):
            for child in node.children:
                if isinstance(child, str):
                    parts.append(child)
                elif child.tag not in UNSEEN and child.tag not in skip:
                    collect(child)
        collect(self)
        return re.sub(r"\s+", " ", "".join(parts)).strip()


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.at = Node("#root")

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.at)
        self.at.children.append(node)
        if tag not in VOID:
            self.at = node

    def handle_startendtag(self, tag, attrs):
        self.at.children.append(Node(tag, dict(attrs), self.at))

    def handle_endtag(self, tag):
        node = self.at
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:   # an end tag with no start tag is ignored
            self.at = node.parent

    def handle_data(self, data):
        self.at.children.append(data)


def parse(html):
    builder = _Builder()
    builder.feed(html or "")
    builder.close()
    return builder.root
