#!/usr/bin/env python

from setuptools import setup, find_packages

def _read(fname):
    try:
        with open(fname) as fobj:
            return fobj.read()

    except IOError:
        return ''


setup(
    name='framequery',
    version='0.1.0',
    description='SQL on dataframes',
    long_description=_read("Readme.md"),
    author='Christopher Prohm',
    author_email='mail@cprohm.de',
    license='MIT',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    setup_requires=['pytest-runner'],
    install_requires=['funcparserlib', 'pandas', 'six', 'sqlparse'],
    tests_require=['pytest'],
    classifiers=[
        'Development Status :: 4 - Beta',

        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
    ],
)