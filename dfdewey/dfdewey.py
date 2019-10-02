# -*- coding: utf-8 -*-
# Copyright 2019 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""DFDewey Command-Line Interface."""

import argparse
import os
import subprocess
import tempfile


def parse_args():
  """Argument parsing function.

  Returns:
      Arguments namespace.
  """
  parser = argparse.ArgumentParser()
  parser.add_argument(
      '--no_base64', help='don\'t decode base64', action='store_true')
  parser.add_argument(
      '--no_gzip', help='don\'t process gzip files', action='store_true')
  parser.add_argument(
      '--no_zip', help='don\'t process zip files', action='store_true')
  parser.add_argument('image_file', help='image file to be processed')
  args = parser.parse_args()
  return args


def main():
  """Main DFDewey function."""
  args = parse_args()
  image_path = os.path.abspath(args.image_file)
  output_path = tempfile.mkdtemp()

  cmd = ['bulk_extractor',
         '-o', output_path,
         '-x', 'all',
         '-e', 'strings']
  if not args.no_base64:
    cmd.extend(['-e', 'base64'])
  if not args.no_gzip:
    cmd.extend(['-e', 'gzip'])
  if not args.no_zip:
    cmd.extend(['-e', 'zip'])
  cmd.extend([image_path])
  subprocess.run(cmd)

  # TODO(jxs): Send to ES

if __name__ == '__main__':
  main()
