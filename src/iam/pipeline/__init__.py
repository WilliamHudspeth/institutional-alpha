"""The valuation pipeline.

v0.2.0-alpha: Stages 1-4 (Reverse DCF → Relative → Intrinsic → Triangulation).
v0.2.0-beta will add Stages 5-6 (macro outlier detection and re-run).
v0.2.0 will add Stage 7 (verdict + peer-relative ranking via Damodaran).
"""

from iam.pipeline.orchestrator import ValuationPipeline, PipelineReport

__all__ = ["ValuationPipeline", "PipelineReport"]
