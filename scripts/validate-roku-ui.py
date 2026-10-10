"""Check package references and declarative event hooks beyond BRS syntax."""
import re
from pathlib import Path
import xml.etree.ElementTree as ET
root = Path(__file__).resolve().parents[1] / "roku"
files = list((root / "components").rglob("*.xml"))
names = set()
for file in files:
    tree = ET.parse(file).getroot()
    name = tree.attrib["name"].lower()
    assert name not in names, f"Duplicate component: {name}"
    names.add(name)
    code = ""
    for node in tree.iter():
        uri = node.get("uri", "")
        if uri and (uri.startswith("pkg:/") or node.tag == "script"):
            path = root / uri[5:] if uri.startswith("pkg:/") else file.parent / uri
            assert path.is_file(), f"{file.name}: missing {uri}"
            if node.tag == "script":
                code += path.read_text() + "\n"
    functions = {n.lower() for n in re.findall(r"(?im)^\s*(?:sub|function)\s+(\w+)", code)}
    for field in tree.findall("./interface/field"):
        handler = field.get("onChange")
        if handler:
            assert handler.lower() in functions, f"{file.name}: missing handler {handler}"
    for function in tree.findall("./interface/function"):
        assert function.get("name").lower() in functions, f"{file.name}: missing public function"
    for node in tree.iter("Font"):
        uri = node.get("uri", "")
        assert uri.startswith("pkg:/"), f"{file.name}: custom Font needs a packaged font URI"
        path = root / uri[5:]
        assert path.is_file() and path.suffix.lower() in {".ttf", ".otf"}, f"{file.name}: invalid font {uri}"
        assert path.read_bytes()[:4] in {b"\x00\x01\x00\x00", b"OTTO"}, f"{file.name}: invalid font header"
        assert int(node.get("size", "0")) > 0, f"{file.name}: invalid font size"
        assert "bold" not in node.attrib, f"{file.name}: use a bold font file, not an unsupported bold field"
    for node in tree.iter("Poster"):
        if node.get("id") in {"art", "artA", "artB"}:
            assert float(node.get("loadWidth", "0")) > 0
            assert float(node.get("loadHeight", "0")) > 0
assert {"homeview","heropanel","mediarows","moviecard","topnavigation"} <= names
print(f"PASS: {len(files)} XML components, asset references, handlers, font sources, artwork decode bounds")
