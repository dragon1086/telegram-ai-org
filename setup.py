"""Minimal setup.py shim — all configuration is in pyproject.toml.

This file exists only for backward compatibility with tools that do not yet
support PEP 517/518 (e.g., older pip versions, some CI systems).

For local development:
    pip install -e .

For building distributions:
    python -m build --wheel --sdist
"""
from setuptools import setup

if __name__ == "__main__":
    setup()
