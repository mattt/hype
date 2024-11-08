"""
This example shows how to construct a simple text analysis tool using Hype.

Download `uv` to run this example: https://github.com/astral-sh/uv

```
uv run examples/text_analysis.py
```
"""

# /// script
# dependencies = [
#   "hype @ git+https://github.com/mattt/hype.git",
#   "textstat",
# ]
# ///

from pydantic import BaseModel, Field
from textstat import flesch_reading_ease, lexicon_count

import hype


class TextAnalysis(BaseModel):
    word_count: int = Field(description="Total number of words in text")
    reading_ease: float = Field(
        description="Flesch reading ease score (0-100, higher is easier)"
    )


@hype.up
def analyze(
    text: str = Field(
        description="Text to analyze",
        max_length=10000,
    ),
) -> TextAnalysis:
    """
    Performs sentiment and readability analysis on text.

    :param text: The text to analyze (must be at least 10 characters)
    :return: Analysis including sentiment scores and readability metrics
    """

    word_count = lexicon_count(text)
    reading_ease = flesch_reading_ease(text) if word_count > 0 else 0

    return TextAnalysis(
        word_count=word_count,
        reading_ease=max(0, min(100, reading_ease)),
    )


if __name__ == "__main__":
    hype.create_gradio_interface(analyze).launch()
