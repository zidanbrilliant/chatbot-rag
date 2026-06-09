import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.document_processor import parse_document


def test_parse_csv():
    csv_content = "name,age\nAlice,30\nBob,25\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        path = f.name
        f.write(csv_content)
    try:
        result = parse_document(path)
        assert len(result) > 0
        text = result[0]["text"]
        assert "name" in text
        assert "Alice" in text
        assert "Bob" in text
    finally:
        os.unlink(path)


def test_unsupported_extension():
    with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
        path = f.name
    try:
        parse_document(path)
        raise AssertionError("Expected ValueError")
    except ValueError:
        pass
    finally:
        os.unlink(path)
