from setuptools import setup
from Cython.Build import cythonize
from os import path

setup(
    name="Logistics",
    ext_modules=cythonize([
        path.join(".", "modules", "*.pyx")
    ])
)
