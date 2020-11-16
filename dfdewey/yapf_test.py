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
"""Enforce code style with YAPF."""

import os
import subprocess
import unittest


class StyleTest(unittest.TestCase):
  """Enforce code style requirements."""

  def testCodeStyle(self):
    """Check YAPF style enforcement runs cleanly."""
    dfdewey_path = os.path.abspath(os.path.dirname(__file__))
    config_path = os.path.join(dfdewey_path, '..', '.style.yapf')
    try:
      subprocess.check_output(
          ['yapf', '--style', config_path, '--diff', '-r', dfdewey_path])
    except subprocess.CalledProcessError as e:
      if hasattr(e, 'output'):
        raise Exception(
            'Run "yapf --style {0:s} -i -r {1:s}" '
            'to correct these problems: {2:s}'.format(
                config_path, dfdewey_path, e.output.decode('utf-8'))) from e
      raise


if __name__ == '__main__':
  unittest.main()
