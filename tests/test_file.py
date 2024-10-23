import pytest
from pydantic import ValidationError

from hype.types.file import File, HttpUrl


def test_from_bytes():
    data = b"test data"
    file = File.from_bytes(data, content_type="text/plain", name="test.txt")
    assert file.data == data
    assert file.content_type == "text/plain"
    assert file.name == "test.txt"


def test_from_path(tmp_path):
    path = tmp_path / "test.txt"
    path.write_bytes(b"test data")
    file = File.from_path(path, content_type="text/plain", name="test.txt")
    assert file.data == b"test data"
    assert file.content_type == "text/plain"
    assert file.name == "test.txt"


def test_from_file():
    original_file = File.from_bytes(
        b"test data", content_type="text/plain", name="test.txt"
    )
    file = File.from_file(original_file)
    assert file.data == original_file.data
    assert file.content_type == original_file.content_type
    assert file.name == original_file.name



def test_from_url_http():
    def mock_loader(_url: HttpUrl) -> File:
        return File.from_bytes(b"test data", content_type="text/plain", name="test.txt")

    file = File.from_url("http://example.com/test.txt", loader=mock_loader)
    assert file.data == b"test data"
    assert file.content_type == "text/plain"
    assert file.name == "test.txt"


def test_from_url_data():
    data_url = "data:text/plain;base64,dGVzdCBkYXRh"
    file = File.from_url(data_url)
    assert file.data == b"test data"
    assert file.content_type == "text/plain;charset=US-ASCII"
    assert file.name is None


def test_size_property():
    file = File.from_bytes(b"test data")
    assert file.size == 9
    empty_file = File.from_bytes(b"")
    assert empty_file.size == 0

    with pytest.raises(ValidationError, match="Input should be a valid bytes"):
        File.from_bytes(None)  # type: ignore
