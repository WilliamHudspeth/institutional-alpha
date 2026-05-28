"""Sanity checks for package structure and imports.

If these tests fail, it means files are missing, misplaced, or
__init__.py files are incorrectly configured (e.g., ModuleNotFoundError).
"""


def test_import_core_data():
    from iam.data import Security

    assert Security is not None


def test_import_thesis_engine():
    from iam.thesis import ThesisEngine

    assert ThesisEngine is not None


def test_import_bayesian_components():
    from iam.thesis.bayesian.priors import ScenarioPrior

    assert ScenarioPrior is not None


def test_import_valuation_pipeline():
    from iam.pipeline import ValuationPipeline

    assert ValuationPipeline is not None
