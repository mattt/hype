from pydantic import Field

import hype


@hype.up
def divide(x: int, y: int = Field(gt=0)) -> int:
    """
    Divides one number by another.
    :param x: The numerator
    :param y: The denominator
    :return: The quotient
    """
    return x // y


if __name__ == "__main__":
    hype.create_gradio_interface(divide).launch()
