from pydantic import BaseModel
from typing import Tuple


class Product(BaseModel):
    name: str
    id: int
    # target_coordinates: Tuple[float, float]
