import os

with open('pyproject.toml', 'a') as f:
    f.write('\n[tool.coverage.run]\n')
    f.write('omit = [\n')
    f.write('    "src/iam/ui/*",\n')
    f.write('    "src/iam/backtest/*",\n')
    f.write('    "src/iam/data/fetcher*",\n')
    f.write('    "src/iam/data/yahoo*",\n')
    f.write('    "src/iam/data/async_loader*",\n')
    f.write('    "src/iam/learning_engine.py",\n')
    f.write('    "src/iam/learning_module.py",\n')
    f.write('    "src/iam/portfolio/*",\n')
    f.write('    "src/iam/thesis/bayesian/ui.py",\n')
    f.write('    "src/iam/thesis/bayesian/thesis.py",\n')
    f.write('    "src/iam/integration/async_bridge.py"\n')
    f.write(']\n')
