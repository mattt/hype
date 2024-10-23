import pytest

from hype.types.data import parse_data_url


def test_parse_data_url():
    url = "data:,A%20brief%20note"
    content_type, data = parse_data_url(url)
    assert content_type == "text/plain;charset=US-ASCII"
    assert data == b"A brief note"


def test_parse_data_url_plain_text():
    url = "data:text/plain,Hello%2C%20World%21"
    content_type, data = parse_data_url(url)
    assert content_type == "text/plain;charset=US-ASCII"
    assert data == b"Hello, World!"


def test_parse_data_url_plain_text_charset_iso_8859_7_encoding():
    url = "data:text/plain;charset=iso-8859-7,%be%d3%be"
    content_type, data = parse_data_url(url)
    assert content_type == "text/plain;charset=iso-8859-7"
    assert data == b"\xbe\xd3\xbe"


def test_parse_data_url_plain_text_charset_utf_8_encoding():
    url = "data:text/plain;charset=utf-8,Hello%2C%20World%21"
    content_type, data = parse_data_url(url)
    assert content_type == "text/plain;charset=utf-8"
    assert data == b"Hello, World!"


def test_parse_data_url_plain_text_base64_encoding():
    url = "data:text/plain;base64,SGVsbG8sIFdvcmxkIQ=="
    content_type, data = parse_data_url(url)
    assert content_type == "text/plain;charset=US-ASCII"
    assert data == b"Hello, World!"


def test_parse_data_url_invalid():
    url = "invalid"
    with pytest.raises(ValueError, match="Invalid data URL format"):
        parse_data_url(url)


def test_parse_data_url_image_gif_base64_encoding():
    url = (
        "data:image/gif;base64,R0lGODdhMAAwAPAAAAAAAP///ywAAAAAMAAw"
        "AAAC8IyPqcvt3wCcDkiLc7C0qwyGHhSWpjQu5yqmCYsapyuvUUlvONmOZtfzgFz"
        "ByTB10QgxOR0TqBQejhRNzOfkVJ+5YiUqrXF5Y5lKh/DeuNcP5yLWGsEbtLiOSp"
        "a/TPg7JpJHxyendzWTBfX0cxOnKPjgBzi4diinWGdkF8kjdfnycQZXZeYGejmJl"
        "ZeGl9i2icVqaNVailT6F5iJ90m6mvuTS4OK05M0vDk0Q4XUtwvKOzrcd3iq9uis"
        "F81M1OIcR7lEewwcLp7tuNNkM3uNna3F2JQFo97Vriy/Xl4/f1cf5VWzXyym7PH"
        "hhx4dbgYKAAA7"
    )
    content_type, data = parse_data_url(url)
    assert content_type == "image/gif"
    assert data.startswith(b"GIF87a")
