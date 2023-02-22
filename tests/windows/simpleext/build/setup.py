import pathlib
import sys
from setuptools import setup, Extension

this_dir = pathlib.Path(__file__).parent

setup(
    name='simpleext',
    version='0.0.1',
    url='https://github.com/adang1345/delvewheel',
    author='Aohan Dang',
    author_email='adang1345@gmail.com',
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: Implementation :: CPython',
    ],
    license='MIT',
    description='Simple extension module',
    python_requires='==3.10.*',
    zip_safe=False,
    ext_modules=[Extension(
        name='simpleext',
        sources=['simpleext.c'],
        include_dirs=['testlib'],
        library_dirs=['testlib'],
        libraries=['testlib'],
    )]
)
