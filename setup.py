"""Set package repository information."""
import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="synchole",
    version="0.1.0",
    author="Andrew M. Hogan",
    author_email="drewthedruid@gmail.com",
    description="Basic framework for asynchronous task communication & management.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Andrew-Hogan/synchole",
    packages=setuptools.find_packages(),
    install_requires=[],
    platforms=['any'],
    classifiers=[
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Utilities",
    ],
)
