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
"""Tests for PostgreSQL datastore."""

import unittest
import mock

from dfdewey.datastore.postgresql import PostgresqlDataStore


class PostgresqlTest(unittest.TestCase):
  """Tests for PostgreSQL datastore."""

  def _get_datastore(self):
    """Get a mock postgresql datastore.

    Returns:
      Mock postgresql datastore.
    """
    with mock.patch('psycopg2.connect') as _:
      db = PostgresqlDataStore(autocommit=True)
    return db

  @mock.patch('psycopg2.extras.execute_values')
  def test_bulk_insert(self, mock_execute_values):
    """Test bulk insert method."""
    db = self._get_datastore()
    rows = [(1, 1), (2, 2), (3, 3)]
    db.bulk_insert('blocks (block, inum)', rows)

    expected_sql = 'INSERT INTO blocks (block, inum) VALUES %s ON CONFLICT DO NOTHING'
    mock_execute_values.assert_called_once_with(db.cursor, expected_sql, rows)

  def test_execute(self):
    """Test execute method."""
    db = self._get_datastore()
    command = (
        'CREATE TABLE images (image_path TEXT, image_hash TEXT PRIMARY KEY)')
    with mock.patch.object(db.cursor, 'execute') as mock_execute:
      db.execute(command)
      mock_execute.assert_called_once_with(command)

  def test_query(self):
    """Test query method."""
    db = self._get_datastore()
    query = 'SELECT filename FROM files WHERE inum = 0'
    with mock.patch.object(db.cursor, 'fetchall', return_value=[('$MFT',)]):
      results = db.query(query)

    self.assertEqual(results, [('$MFT',)])

  def test_query_single_row(self):
    """Test query single row method."""
    db = self._get_datastore()
    query = (
        'SELECT 1 from image_case WHERE image_hash = '
        '\'d41d8cd98f00b204e9800998ecf8427e\'')
    with mock.patch.object(db.cursor, 'fetchone', return_value=(1,)):
      results = db.query_single_row(query)

    self.assertEqual(results, (1,))

  def test_switch_database(self):
    """Test switch database method."""
    db = self._get_datastore()
    with mock.patch('psycopg2.connect') as mock_connect:
      db.switch_database(db_name='dfdewey', autocommit=True)
      mock_connect.assert_called_once_with(
          database='dfdewey', user='dfdewey', password='password',
          host='127.0.0.1', port=5432)

  def test_table_exists(self):
    """Test table exists method."""
    db = self._get_datastore()

    with mock.patch.object(db.cursor, 'fetchone', return_value=(1,)):
      result = db.table_exists('images')
    self.assertEqual(result, True)

    with mock.patch.object(db.cursor, 'fetchone', return_value=None):
      result = db.table_exists('images')
    self.assertEqual(result, False)

  def test_value_exists(self):
    """Test value exists method."""
    db = self._get_datastore()

    with mock.patch.object(db.cursor, 'fetchone', return_value=(1,)):
      result = db.value_exists(
          'images', 'image_hash', 'd41d8cd98f00b204e9800998ecf8427e')
    self.assertEqual(result, True)

    with mock.patch.object(db.cursor, 'fetchone', return_value=None):
      result = db.value_exists(
          'images', 'image_hash', 'd41d8cd98f00b204e9800998ecf8427e')
    self.assertEqual(result, False)


if __name__ == '__main__':
  unittest.main()
