import tempfile
from test.conftest import test_config

import pytest
from bs4 import BeautifulSoup
from markdown import markdown

import pptagent.utils as utils
from pptagent.utils import get_json_from_response, split_markdown_to_chunks


def test_extract_json_from_markdown_block():
    """Test extracting JSON from a markdown code block."""
    response = """
    Here's the JSON you requested:

    ```json
    {
        "name": "John",
        "age": 30,
        "city": "New York"
    }
    ```

    Let me know if you need anything else.
    """

    result = get_json_from_response(response)
    assert isinstance(result, dict)
    assert result["name"] == "John"
    assert result["age"] == 30
    assert result["city"] == "New York"


def test_extract_complex_json():
    """Test extracting JSON with minor syntax errors that can be repaired."""
    response = """
```json\n{\n    "table_data": [\n        ["Domain", "", "", "Presentation", "", ""],\n        ["", "#Chars", "#Figs", "#Chars", "#Figs", "#Pages"],\n        ["Culture", "12,708", "2.9", "6,585", "12.8", "14.3"],\n        ["Education", "12,305", "5.5", "3,993", "12.9", "13.9"],\n        ["Science", "16,661", "4.8", "5,334", "24.0", "18.4"],\n        ["Society", "13,019", "7.3", "3,723", "9.8", "12.9"],\n        ["Tech", "18,315", "11.4", "5,325", "12.9", "16.8"]\n    ],\n    "merge_area": [\n        [0, 0, 0, 5],\n        [1, 0, 1, 1],\n        [1, 3, 1, 5]\n    ]\n}\n```
    """

    result = get_json_from_response(response)
    assert isinstance(result, dict)
    assert result["table_data"] == [
        ["Domain", "", "", "Presentation", "", ""],
        ["", "#Chars", "#Figs", "#Chars", "#Figs", "#Pages"],
        ["Culture", "12,708", "2.9", "6,585", "12.8", "14.3"],
        ["Education", "12,305", "5.5", "3,993", "12.9", "13.9"],
        ["Science", "16,661", "4.8", "5,334", "24.0", "18.4"],
        ["Society", "13,019", "7.3", "3,723", "9.8", "12.9"],
        ["Tech", "18,315", "11.4", "5,325", "12.9", "16.8"],
    ]
    assert result["merge_area"] == [[0, 0, 0, 5], [1, 0, 1, 1], [1, 3, 1, 5]]


def test_extract_nested_json():
    """Test extracting nested JSON objects."""
    response = """
    Here's the JSON:

    {
        "person": {
            "name": "John",
            "age": 30
        },
        "address": {
            "city": "New York",
            "zip": "10001"
        }
    }
    """

    result = get_json_from_response(response)
    assert isinstance(result, dict)
    assert result["person"]["name"] == "John"
    assert result["address"]["city"] == "New York"


def test_json_not_found():
    """Test that an exception is raised when JSON is not found."""
    response = "This is just plain text with no JSON."

    with pytest.raises(Exception) as excinfo:
        get_json_from_response(response)

    assert "JSON not found" in str(excinfo.value)


def test_ppt_to_images_conversion():
    """Test converting a PPTX file to images."""
    # Run the conversion
    utils.ppt_to_images(test_config.ppt, tempfile.mkdtemp())


def test_markdown_splits():
    markdown_content = open(f"{test_config.document}/source.md").read()
    chunks = split_markdown_to_chunks(markdown_content)
    assert len(chunks) == 5
    markdown_html = markdown(markdown_content, extensions=["tables"])
    soup = BeautifulSoup(markdown_html, "html.parser")
    num_medias = len(soup.find_all("img")) + len(soup.find_all("table"))
    parsed_medias = 0
    for chunk in chunks:
        markdown_html = markdown(chunk["content"], extensions=["tables"])
        soup = BeautifulSoup(markdown_html, "html.parser")
        parsed_medias += len(soup.find_all("img")) + len(soup.find_all("table"))
    assert parsed_medias == num_medias
