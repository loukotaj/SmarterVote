from setuptools import setup, find_packages

setup(
    name="smartervote-schema",
    version="0.2.0",
    description="Shared Pydantic models for SmarterVote project",
    packages=find_packages(),
    install_requires=[
        "pydantic>=2.0.0",
    ],
    python_requires=">=3.10",
)
