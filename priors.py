from dataclasses import dataclass


@dataclass
class ScenarioPrior:
    """Represents the probability of a specific scenario (e.g., Bull, Base, Bear)."""
    label: str
    probability: float

    def __post_init__(self):
        self.probability = max(0.0, min(1.0, self.probability))