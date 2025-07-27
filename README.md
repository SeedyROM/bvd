# 🚨 BVD (Breaking Version Detector) 🔍

An extensible tool for detecting breaking dependency version changes in configuration files. BVD analyzes git diffs to identify potentially dangerous version upgrades and unbound version constraints that could lead to unexpected breaking changes. ⚡

## 📦 Installation

### 🚀 Using uv (Recommended)

BVD uses [uv](https://docs.astral.sh/uv/) for fast, reliable Python dependency management. ⚡

#### 🛠️ Install uv first:
```bash
# On macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or with pip
pip install uv
```

#### 🎯 Install BVD:
```bash
# Clone the repository
git clone https://github.com/SeedyROM/bvd
cd bvd

# Install in development mode with all dependencies
uv sync --dev

# TODO(SeedyROM): This is wrong!
# # Or install just the package
# uv add bvd
```

### 🐍 Using pip
```bash
pip install bvd
```

## 🎮 Usage

### 💻 Command Line Interface

#### Using Makefile (Development Environment) 🛠️
```bash
# Run on specific files
make run -- --files example.tf

# Run on multiple files
make run -- --files config.tf variables.tf

# Show help
make run -- --help

# Run with verbose output
make run -- --files example.tf --verbose
```

#### Direct Usage 🎯
```bash
# Run on specific files
uv run bvd --files example.tf

# Or if installed globally
bvd --files example.tf

# Show help
uv run bvd --help
```

### 🔧 Development Commands

This project uses `uv` for dependency management and `make` for common development tasks: ⚙️

- `make format` - Format code with black ✨
- `make lint` - Check code style and quality with ruff 🔍
- `make lint-fix` - Fix code style issues automatically 🔧
- `make test` - Run all tests with pytest 🧪
- `make run -- --files example.tf` - Run bvd on specific files 🎯
- `make run -- --help` - Show bvd help ❓


**See [Makefile](Makefile) for all available/source of truth commands on POSIX systems.** 📋

## ✨ Features

- **Multi-format Support**: Extensible parser system supports Terraform and more 🔧
- **Git Integration**: Analyzes changes between git references 🌳
- **Severity Levels**: Configurable issue severity and critical package detection ⚠️
- **Comprehensive Testing**: 97.99% test coverage with performance and integration tests 🎯

## 📄 Supported File Formats

- **Terraform** (`.tf`) - Provider version detection and analysis 🏗️

## 🏛️ Architecture

### ⚙️ Core Components

- **`src/bvd/core.py`** - Main logic with `VersionDetector` class 🧠
- **`src/bvd/cli.py`** - Click-based command-line interface 💻
- **`src/bvd/parsers/`** - Extensible parser system for different file formats 🔧

### 🔌 Extension

To add support for new file formats, create a parser in `src/bvd/parsers/` that inherits from `DependencyParser`. 🛠️

## 📚 Dependencies

- **packaging** - For semver parsing and comparison 📦
- **python-hcl2** - For parsing Terraform HCL files 🏗️
- **click** - For CLI interface 🖱️

## 🧪 Testing

Run the comprehensive test suite: 🚀
```bash
make test              # Run all tests 🧪
make test-cov          # Run with coverage report 📊
make test -- --verbose # Verbose test output 📢
```
