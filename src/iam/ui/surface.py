from abc import ABC, abstractmethod
from typing import List
from .scene import Plane, Marker, Annotation

class SurfaceModel(ABC):
    title: str = "Untitled"
    x_axis_name: str = "X"
    y_axis_name: str = "Y"
    z_axis_name: str = "Z"
    x_min: float = 0.0
    x_max: float = 1.0
    y_min: float = 0.0
    y_max: float = 1.0
    z_min: float = 0.0
    z_max: float = 1.0

    @abstractmethod
    def generate_z_grid(self) -> List[List[float]]:
        """Returns a 2D grid of Z values. First index = y (row), second = x (col)."""
        ...

    def get_planes(self) -> List[Plane]:
        return []

    def get_markers(self) -> List[Marker]:
        return []

    def get_annotations(self) -> List[Annotation]:
        return []
