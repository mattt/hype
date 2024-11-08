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

from pydantic import BaseModel, Field, field_validator
from textstat import flesch_reading_ease, lexicon_count

import hype


class TextAnalysis(BaseModel):
    word_count: int = Field(description="Total number of words in text")
    reading_ease: float = Field(
        description="Flesch reading ease score (0-100, higher is easier)"
    )

    @field_validator('reading_ease')
    def clamp_reading_ease(cls, v: float) -> float:
        """Clamp reading ease score between 0 and 100"""
        return max(0, min(100, v))


@hype.up
def analyze(
    text: str = Field(
        description="Text to analyze",
        max_length=10000,
    ),
) -> TextAnalysis:
    """Performs sentiment and readability analysis on text."""

    word_count = lexicon_count(text)
    reading_ease = flesch_reading_ease(text) if word_count > 0 else 0

    return TextAnalysis(
        word_count=word_count,
        reading_ease=reading_ease,
    )


if __name__ == "__main__":
    hype.create_gradio_interface(analyze).launch()
