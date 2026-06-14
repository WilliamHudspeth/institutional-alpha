from abc import ABC, abstractmethod

from .scene import Annotation, Marker, Plane


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
    def generate_z_grid(self) -> list[list[float]]:
        """Returns a 2D grid of Z values. First index = y (row), second = x (col)."""
        ...

    def get_planes(self) -> list[Plane]:
        return []

    def get_markers(self) -> list[Marker]:
        return []

    def get_annotations(self) -> list[Annotation]:
        return []
