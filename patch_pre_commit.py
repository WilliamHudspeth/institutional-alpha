import sys

with open('.pre-commit-config.yaml', 'r') as f:
    content = f.read()

bandit_config = """  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.5
    hooks:
      - id: bandit
        args: ["-c", "pyproject.toml", "-r", "src"]
        additional_dependencies: ["bandit[toml]"]

"""

# Insert before ci:
content = content.replace('ci:', bandit_config + 'ci:')

with open('.pre-commit-config.yaml', 'w') as f:
    f.write(content)
