import os.path
from setuptools import Extension, setup

this_dir = os.path.dirname(__file__)

setup(
    ext_modules=[Extension(
        name='testwheel',
        sources=['testwheel.c'],
        include_dirs=[os.path.join(this_dir, 'testdep')],
        library_dirs=[os.path.join(this_dir, 'testdep')],
        libraries=['testdep'],
        py_limited_api=True,
    )]
)
