import math
from dataclasses import dataclass
from typing import Tuple

@dataclass
class Point3D:
    x: float
    y: float
    z: float

@dataclass
class Point2D:
    x: float
    y: float

class Camera:
    def __init__(self, angle_z: float = 0.785, angle_x: float = 0.610, scale: float = 1.0, offset_x: float = 0.0, offset_y: float = 0.0):
        """
        angle_z: rotation around the vertical axis (yaw)
        angle_x: rotation around the horizontal axis (pitch)
        """
        self.angle_z = angle_z
        self.angle_x = angle_x
        self.scale = scale
        self.offset_x = offset_x
        self.offset_y = offset_y

    def project(self, p: Point3D) -> Tuple[Point2D, float]:
        """Projects a 3D point to 2D terminal coordinates, returning the 2D point and its depth for Z-sorting."""
        # 1. Rotate around Z (yaw)
        cz = math.cos(self.angle_z)
        sz = math.sin(self.angle_z)
        rx = p.x * cz - p.y * sz
        ry = p.x * sz + p.y * cz
        
        # 2. Rotate around X (pitch)
        cx = math.cos(self.angle_x)
        sx = math.sin(self.angle_x)
        
        ry2 = ry * cx - p.z * sx
        rz = ry * sx + p.z * cx  # Depth
        
        # 3. Scale and offset
        # Multiply X by 2 because terminal characters are roughly twice as tall as they are wide
        screen_x = (rx * self.scale * 2.0) + self.offset_x
        screen_y = (ry2 * self.scale) + self.offset_y
        
        return Point2D(screen_x, screen_y), rz
