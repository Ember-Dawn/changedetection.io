"""An optional local extension; original dgtlmoon plugin remains installed unchanged."""
from setuptools import setup, find_packages

setup(
    name='changedetection-cloak-shared',
    version='0.1.0',
    description='Shared persistent CloakBrowser backend for changedetection.io',
    packages=find_packages(),
    python_requires='>=3.10',
    install_requires=[],  # Dependencies supplied by Dockerfile.cloakbrowser
    entry_points={
        'changedetectionio': [
            'cloak_shared = changedetection_cloak_shared.plugin',
        ],
    },
)
