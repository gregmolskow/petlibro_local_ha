# Python Project Template

Modern Python project template with automated CI/CD, semantic versioning, and documentation.

## Features

- 🚀 **Fast dependency management** with [uv](https://github.com/astral-sh/uv)
- 🔍 **Code quality** via [Ruff](https://github.com/astral-sh/ruff) linting & formatting
- 🧪 **Testing** with pytest and coverage
- 📦 **Semantic versioning** based on commit messages
- 🎁 **Automated releases** with Python wheels
- 📚 **Documentation** deployment to GitHub Pages

## Quick Start
First, make sure uv is installed on your system.
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then, use this repo as a template for your code! Once your code repo has been initalized, follow the setup steps outlined in the next section.

**Setup:**
1. **Edit `pyproject.toml`**: 
   - Change `name = "my-project"` to your project name
   - Update `packages = ["src/my_project"]` to match your package directory
2. **Create project structure**:
   ```
   mkdir -p src/<my_project> tests docs/source
   touch src/<my_project>/__init__.py
   ```
3. Enable GitHub Pages in repo settings (source: GitHub Actions)

## Project Structure

```
├── .github/workflows/
│   ├── ci.yml                 # Main pipeline orchestrator
│   ├── ruff-lint.yml         # Linting & testing
│   ├── semantic-version.yml  # Version management
│   ├── build-release.yml     # Package building
│   └── docs.yml              # Documentation
├── .releaserc.json           # Semantic release config
├── VERSION                   # Current version
├── pyproject.toml            # Project configuration
├── src/                      # Source code
├── tests/                    # Tests
└── docs/                     # Sphinx docs
```

## CI/CD Pipeline

**Pull Requests:** Verifies linting, tests, builds (no releases)  
**Main Branch:** Full pipeline with releases and documentation deployment

## Commit Message Format

Use [Conventional Commits](https://www.conventionalcommits.org/) for automatic versioning:

```bash
feat: add feature          # Minor bump (0.1.0 → 0.2.0)
fix: fix bug              # Patch bump (0.1.0 → 0.1.1)
feat!: breaking change    # Major bump (0.1.0 → 1.0.0)
docs: update docs         # Patch bump
chore: update deps        # No release
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`

## Development Commands

```bash
# Testing
uv run pytest
uv run pytest --cov=src

# Linting
uv run ruff check .
uv run ruff format .

# Build docs
cd docs && uv run sphinx-build -b html source build/html

# Build package
uv build
```

## Configuration

- **`pyproject.toml`**: Project metadata, dependencies, tool configs
- **`.releaserc.json`**: Semantic release rules
- **`VERSION`**: Current version (auto-updated)

### GitHub Packages

Python packages are automatically published to GitHub Packages on releases. To install from GitHub Packages:

```bash
# Configure uv to use GitHub Packages
uv pip install your-package --index-url https://maven.pkg.github.com/USERNAME/index/
```

No additional configuration needed - uses `GITHUB_TOKEN` automatically!

## Resources

- [uv](https://github.com/astral-sh/uv) | [Ruff](https://docs.astral.sh/ruff/) | [Conventional Commits](https://www.conventionalcommits.org/)
- [Semantic Release](https://semantic-release.gitbook.io/) | [Sphinx](https://www.sphinx-doc.org/)

---

**Happy coding! 🚀**
