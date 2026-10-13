"""Generate LocalJev.ipynb from its readable Markdown source."""
import hashlib
import argparse
import copy
import re
from pathlib import Path
import nbformat

ROOT = Path(__file__).resolve().parents[1] / "LocalJev"


def build(preserve_outputs=False):
    source = (ROOT / "LocalJev.md").read_text(encoding="utf-8")
    cells, end = [], 0
    for match in re.finditer(r"^```python\n(.*?)^```[ \t]*$", source, re.MULTILINE | re.DOTALL):
        prose = source[end:match.start()].strip()
        if prose:
            cells.append(nbformat.v4.new_markdown_cell(prose))
        cells.append(nbformat.v4.new_code_cell(match.group(1).rstrip()))
        end = match.end()
    if source[end:].strip():
        cells.append(nbformat.v4.new_markdown_cell(source[end:].strip()))
    for i, cell in enumerate(cells):
        cell.id = hashlib.sha256(f"local-jev:{i}:{cell.source}".encode()).hexdigest()[:12]
    metadata = {}
    destination = ROOT / "LocalJev.ipynb"
    if preserve_outputs and destination.exists():
        previous = nbformat.read(destination, as_version=4)
        metadata = copy.deepcopy(previous.metadata)
        prior_cells = {(cell.cell_type, cell.source): cell for cell in previous.cells}
        for cell in cells:
            old = prior_cells.get((cell.cell_type, cell.source))
            if old is not None:
                cell.metadata = copy.deepcopy(old.metadata)
                if cell.cell_type == "code":
                    cell.outputs = copy.deepcopy(old.outputs)
                    cell.execution_count = old.execution_count
    metadata["kernelspec"] = {"display_name": "Python 3 (ipykernel)", "language": "python", "name": "python3"}
    nb = nbformat.v4.new_notebook(cells=cells, metadata=metadata)
    nbformat.validate(nb)
    nbformat.write(nb, destination)
    print(f"生成 LocalJev.ipynb：{len(cells)} 个单元格")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preserve-outputs", action="store_true")
    build(parser.parse_args().preserve_outputs)
