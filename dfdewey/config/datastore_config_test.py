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
"""Tests for datastore config."""

import os
import tempfile
import unittest

import mock

import dfdewey.config as dfdewey_config


class DatastoreConfigTest(unittest.TestCase):
  """Tests for datastore config."""

  def setUp(self):
    self.config_file = tempfile.mkstemp()[1]

  def tearDown(self):
    os.remove(self.config_file)

  def _write_config(self, text, config_file=None):
    """Helper to write text to a configuration file.

    Args:
      text(str): data to write to the file.
      config_file(str): Alternate path to write config file to.
    """
    if not config_file:
      config_file = self.config_file
    with open(config_file, 'w') as config_file_handle:
      config_file_handle.write(text)

  @mock.patch('os.environ.get')
  @mock.patch('os.path.exists')
  def test_load_config(self, mock_path_exists, mock_env):
    """Test load config method."""
    # Test if config doesn't exist
    mock_path_exists.return_value = False
    mock_env.return_value = None
    config = dfdewey_config.load_config()
    self.assertIsNone(config)

    # Test specified config file
    config_text = 'PG_HOST = \'127.0.0.1\'\nPG_PORT = 5432'
    self._write_config(config_text)
    config = dfdewey_config.load_config(self.config_file)
    self.assertTrue(hasattr(config, 'PG_HOST'))
    self.assertTrue(hasattr(config, 'PG_PORT'))
    self.assertEqual(config.PG_HOST, '127.0.0.1')
    self.assertEqual(config.PG_PORT, 5432)

    # Test error opening specified config file
    config = dfdewey_config.load_config('/tmp/does-not-exist')
    self.assertIsNone(config)

    # Test loading config from environment variable
    mock_env.return_value = '1234'
    mock_open = mock.mock_open()
    with mock.patch('dfdewey.config.open', mock_open, create=True):
      config = dfdewey_config.load_config()
      mock_open.assert_called_once_with(
          os.path.join(os.path.expanduser('~'), '.dfdeweyrc'), 'w')
      mock_file_handle = mock_open()
      mock_file_handle.write.assert_called_once()
