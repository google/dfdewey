#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""DFDewey setup file."""

import sys

try:
  from setuptools import find_packages, setup
except ImportError:
  from distutils.core import find_packages, setup

try:
  from setuptools.commands.sdist import sdist
except ImportError:
  from distutils.command.sdist import sdist

import dfdewey

version_tuple = (sys.version_info[0], sys.version_info[1])
if version_tuple < (3, 6):
  print((
      'Unsupported Python version: {0:s}, version 3.6 or higher '
      'required.').format(sys.version))
  sys.exit(1)

sys.path.insert(0, '.')

DFDEWEY_DESCRIPTION = (
    'dfDewey is a digital forensics string extraction, indexing, and searching '
    'tool.')

requirements = []
with open('requirements.txt','r') as f:
  requirements = f.read().splitlines()
setup(
    name='dfDewey',
    version=dfdewey.__version__,
    description=DFDEWEY_DESCRIPTION,
    long_description=DFDEWEY_DESCRIPTION,
    license='Apache License, Version 2.0',
    url='https://github.com/google/dfdewey',
    maintainer='dfDewey development team',
    maintainer_email='dfdewey-dev@googlegroups.com',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
    ],
    packages=find_packages(),
    include_package_data=True,
    data_files=[
        ('share/doc/dfdewey', ['AUTHORS', 'LICENSE', 'README.md']),
    ],
    install_requires=requirements,
    extras_require={
        'dev': ['mock', 'pytest', 'yapf', 'coverage']
    },
    entry_points={'console_scripts': ['dfdewey=dfdewey.dfdcli:main']},
    python_requires='>=3.6',
)
