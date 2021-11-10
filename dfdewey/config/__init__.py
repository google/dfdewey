# -*- coding: utf-8 -*-
# Copyright 2021 Google LLC
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
"""DFDewey Config."""

import base64
import imp
import logging
import os

CONFIG_ENV = 'DFDEWEY_CONF'
CONFIG_FILE = '.dfdeweyrc'
# Look in homedir first, then current dir
CONFIG_PATH = [
    os.path.expanduser('~'),
    os.path.dirname(os.path.abspath(__file__)),
]

log = logging.getLogger('dfdewey')


def load_config(config_file=None):
  """Finds dfDewey config file and loads it.

  Args:
    config_file(str): full path to config file
  """
  config = None
  if not config_file:
    log.debug('No config file specified. Looking in default locations.')
    for path in CONFIG_PATH:
      if os.path.exists(os.path.join(path, CONFIG_FILE)):
        config_file = os.path.join(path, CONFIG_FILE)
        break
    if not config_file:
      # If we still don't have a config file, check the environment variable
      config_env = os.environ.get(CONFIG_ENV)
      if config_env:
        config_file = os.path.join(CONFIG_PATH[0], CONFIG_FILE)
        with open(config_file, 'wb') as f:
          f.write(base64.b64decode(config_env))

  if config_file:
    log.debug('Loading config from {0:s}'.format(config_file))
    try:
      config = imp.load_source('config', config_file)
    except IOError as e:
      log.error(
          'Could not load config file {0:s}: {1!s}'.format(config_file, e))

  if not config:
    log.warn('Config file not loaded. Using default datastore settings.')

  return config
