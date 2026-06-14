from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Camera:
    yaw: float = 45.0        # rotation around Z (degrees)
    pitch: float = 30.0     # tilt (0 = top-down, 90 = edge-on)
    zoom: float = 1.0       # scaling factor
    
    def reset(self):
        self.yaw = 45.0
        self.pitch = 30.0
        self.zoom = 1.0

@dataclass
class Plane:
    z: float                # constant Z level
    symbol: str = '~'
    x_range: Optional[tuple[float, float]] = None
    y_range: Optional[tuple[float, float]] = None

@dataclass
class Marker:
    x: float
    y: float
    z: float
    symbol: str = 'X'
    label: str = ''

@dataclass
class Annotation:
    x: float
    y: float
    z: float
    text: str

@dataclass
class Scene:
    surfaces: list = field(default_factory=list)   # list of SurfaceModel
    planes: list = field(default_factory=list)     # list of Plane
    markers: list = field(default_factory=list)    # list of Marker
    annotations: list = field(default_factory=list)# list of Annotation
    camera: Camera = field(default_factory=Camera)
