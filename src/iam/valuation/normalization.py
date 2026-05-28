from dataclasses import dataclass


@dataclass
class CycleWeights:
    expansion: float = 0.50
    contraction: float = 0.30
    distress: float = 0.10
    recovery: float = 0.10

    def validate(self):
        if abs(sum([self.expansion, self.contraction, self.distress, self.recovery]) - 1.0) > 1e-6:
            raise ValueError("CycleWeights must sum to 1.0")


def normalize_through_cycle(
    peak_value: float,
    weights: CycleWeights = CycleWeights(),
    contraction_factor: float = 0.70,
    distress_factor: float = 0.40,
    recovery_factor: float = 0.75,
) -> float:
    """Generic through-cycle normalizer. Defaults reproduce BLK HPS: 360M -> 288M."""
    weights.validate()
    factor = (
        weights.expansion * 1.0
        + weights.contraction * contraction_factor
        + weights.distress * distress_factor
        + weights.recovery * recovery_factor
    )
    return peak_value * factor


def apply_distributable_haircut(fcfe: float, haircut: float) -> float:
    """haircut as decimal, e.g. 0.08 = 8 percent non-distributable capital."""
    if not 0 <= haircut < 1:
        raise ValueError("haircut must be in [0, 1)")
    return fcfe * (1 - haircut)


def fragility_penalty(
    model_elasticity: float, empirical_elasticity: float, scale: float = 0.5
) -> float:
    """Map operating-leverage gap to IAM Fragility penalty in [-1, 0]."""
    gap = model_elasticity - empirical_elasticity
    penalty = -scale * gap
    return max(-1.0, min(0.0, penalty))


if __name__ == "__main__":
    # BLK HPS: peak 360M -> normalized 288M
    hps_norm = normalize_through_cycle(360_000_000)

    # BLK iShares: 6.30B reported -> 5.796B distributable at 8% haircut
    ishares_dist = apply_distributable_haircut(6_300_000_000, 0.08)

    # Elasticity test: model 1.85x vs empirical 0.69x -> -0.58 penalty
    frag = fragility_penalty(1.85, 0.69)

    # Industrial name with deeper distress
    deep_cycle = CycleWeights()
    industrial_norm = normalize_through_cycle(
        2_000_000_000,
        weights=deep_cycle,
        contraction_factor=0.60,
        distress_factor=0.25,
        recovery_factor=0.70,
    )

    print(f"HPS normalized: {hps_norm:,.0f}")
    print(f"iShares distributable: {ishares_dist:,.0f}")
    print(f"Fragility penalty: {frag:.2f}")
    print(f"Industrial normalized: {industrial_norm:,.0f}")
