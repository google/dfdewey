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

import importlib.machinery
import importlib.util
import logging
import os

CONFIG_ENV = [
    'PG_HOST', 'PG_PORT', 'PG_DB_NAME', 'OS_HOST', 'OS_PORT', 'OS_URL'
]
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
      # If we still don't have a config file, check the environment variables
      valid_config = True
      config_str = ''
      for config_var in CONFIG_ENV:
        config_env = os.environ.get('_'.join(('DFDEWEY', config_var)))
        if not config_env:
          if config_var == 'OS_URL':
            config_str += '{0:s} = {1:s}\n'.format(config_var, 'None')
            break
          else:
            valid_config = False
            break
        if 'PORT' in config_var:
          config_str += '{0:s} = {1:d}\n'.format(config_var, int(config_env))
        else:
          config_str += '{0:s} = \'{1:s}\'\n'.format(config_var, config_env)

      if valid_config:
        config_file = os.path.join(CONFIG_PATH[0], CONFIG_FILE)
        with open(config_file, 'w') as f:
          f.write(config_str)

  if config_file:
    log.debug('Loading config from {0:s}'.format(config_file))
    try:
      spec = importlib.util.spec_from_loader(
          'config', importlib.machinery.SourceFileLoader('config', config_file))
      config = importlib.util.module_from_spec(spec)
      spec.loader.exec_module(config)
    except FileNotFoundError as e:
      log.error(
          'Could not load config file {0:s}: {1!s}'.format(config_file, e))
      config = None

  if not config:
    log.warning('Config file not loaded. Using default datastore settings.')

  return config
