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

from setuptools import find_packages
from setuptools import setup

import dfdewey

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
    license='Apache License, Version 2.0',
    maintainer='dfDewey development team',
    maintainer_email='dfdewey-dev@googlegroups.com',
    packages=find_packages(),
    include_package_data=True,
    install_requires=requirements,
    extras_require={
        'dev': ['mock', 'nose', 'yapf', 'coverage']
    }
)
