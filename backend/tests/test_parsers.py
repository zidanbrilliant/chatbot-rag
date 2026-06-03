import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.document_processor import parse_document


def create_csv(content):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
    f.write(content)
    f.close()
    return f.name


def test_parse_csv():
    csv_content = "name,age\nAlice,30\nBob,25\n"
    path = create_csv(csv_content)
    result = parse_document(path)
    assert "name" in result
    assert "Alice" in result
    assert "Bob" in result
    os.unlink(path)


def test_unsupported_extension():
    f = tempfile.NamedTemporaryFile(suffix=".xyz", delete=False)
    f.close()
    try:
        parse_document(f.name)
        assert False, "Expected ValueError"
    except ValueError:
        pass
    os.unlink(f.name)
