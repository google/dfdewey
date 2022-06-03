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
"""PostgreSQL datastore."""

import psycopg2
from psycopg2 import extras


class PostgresqlDataStore():
  """Implements the datastore."""

  def __init__(
      self, host='127.0.0.1', port=5432, db_name='dfdewey', autocommit=False):
    """Create a PostgreSQL client."""
    super().__init__()
    try:
      self.db = psycopg2.connect(
          database=db_name, user='dfdewey', password='password', host=host,
          port=port)
    except psycopg2.OperationalError as e:
      raise RuntimeError('Unable to connect to PostgreSQL.') from e
    if autocommit:
      self.db.set_isolation_level(
          psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    self.cursor = self.db.cursor()

  def __del__(self):
    """Finalise a PostgreSQL client."""
    try:
      self.db.commit()
      self.db.close()
    except AttributeError:
      pass

  def _execute(self, command):
    """Execute a command in the PostgreSQL database.

    Args:
      command: The SQL command to be executed
    """
    self.cursor.execute(command)

  def _query(self, query):
    """Query the database.

    Args:
      query: SQL query to execute

    Returns:
      Rows returned by the query
    """
    self.cursor.execute(query)

    return self.cursor.fetchall()

  def _query_single_row(self, query):
    """Query the database for a single row.

    Args:
      query: SQL query to execute

    Returns:
      Single row returned by the query
    """
    self.cursor.execute(query)

    return self.cursor.fetchone()

  def bulk_insert(self, table_spec, rows):
    """Execute a bulk insert into a table.

    Args:
      table_spec: String in the form 'table_name (col1, col2, ..., coln)'
      rows: Array of value tuples to be inserted
    """
    extras.execute_values(
        self.cursor,
        'INSERT INTO {0:s} VALUES %s ON CONFLICT DO NOTHING'.format(table_spec),
        rows)

  def create_database(self, db_name):
    """Create a database for the image.

    Args:
      db_name: Database name
    """
    self._execute('CREATE DATABASE {0:s}'.format(db_name))

  def create_filesystem_database(self):
    """Create a filesystem database for the image."""
    self._execute((
        'CREATE TABLE blocks (block INTEGER, inum INTEGER, part TEXT, '
        'PRIMARY KEY (block, inum, part))'))
    self._execute((
        'CREATE TABLE files (inum INTEGER, filename TEXT, part TEXT, '
        'PRIMARY KEY (inum, filename, part))'))

  def delete_filesystem_database(self, db_name):
    """Delete the filesystem database for the image.

    Args:
      db_name: The name of the database to drop
    """
    self._execute('DROP DATABASE {0:s}'.format(db_name))

  def delete_image(self, image_id):
    """Delete an image from the database.

    Args:
      image_id: Image identifier
    """
    self._execute(
        'DELETE FROM images WHERE image_id = \'{0:s}\''.format(image_id))

  def get_case_images(self, case):
    """Get all images for the case.

    Args:
      case: Case name

    Returns:
      A dictionary of the images in the case.
    """
    images = {}
    results = self._query((
        'SELECT image_hash, image_path FROM image_case NATURAL JOIN images '
        'WHERE case_id = \'{0:s}\'').format(case))
    for image_hash, image_path in results:
      images[image_hash] = image_path
    return images

  def get_filenames_from_inode(self, inode, location):
    """Gets filename(s) from an inode number.

    Args:
      inode: Inode number of target file
      location: Partition number

    Returns:
      Filename(s) of given inode or None
    """
    results = self._query((
        'SELECT filename FROM files '
        'WHERE inum = {0:d} AND part = \'{1:s}\'').format(inode, location))
    filenames = []
    for result in results:
      filenames.append(result[0])
    return filenames

  def get_image_cases(self, image_id):
    """Get a list of cases the image is linked to.

    Args:
      image_id: Image identifier

    Returns:
      List of cases or None.
    """
    cases = self._query(
        'SELECT case_id FROM image_case WHERE image_id = \'{0:s}\''.format(
            image_id))
    for c in range(len(cases)):
      cases[c] = cases[c][0]
    return cases

  def get_image_hash(self, image_id):
    """Get an image hash from the database.

    Args:
      image_id: Image identifier

    Returns:
      Hash for the image stored in PostgreSQL or None.
    """
    image_hash = self._query_single_row(
        'SELECT image_hash FROM images WHERE image_id = \'{0:s}\''.format(
            image_id))
    if image_hash:
      return image_hash[0]
    else:
      return None

  def get_inodes(self, block, location):
    """Gets inode numbers for a block offset.

    Args:
      block (int): block offset within the image.
      location (str): Partition location / identifier.

    Returns:
      Inode number(s) of the given block or None.
    """
    inodes = self._query(
        ('SELECT inum FROM blocks '
         'WHERE block = {0:d} AND part = \'{1:s}\'').format(block, location))
    for i in range(len(inodes)):
      inodes[i] = inodes[i][0]
    return inodes

  def initialise_database(self):
    """Initialse the image database."""
    self._execute((
        'CREATE TABLE images (image_id TEXT PRIMARY KEY, image_path TEXT, '
        'image_hash TEXT)'))

    self._execute((
        'CREATE TABLE image_case ('
        'case_id TEXT, image_id TEXT REFERENCES images(image_id), '
        'PRIMARY KEY (case_id, image_id))'))

  def insert_image(self, image_id, image_path, image_hash):
    """Add an image to the database.

    Args:
      image_id: Image identifier
      image_path: Path to the image file
      image_hash: Hash of the image
    """
    self._execute((
        'INSERT INTO images (image_id, image_path, image_hash) '
        'VALUES (\'{0:s}\', \'{1:s}\', \'{2:s}\')').format(
            image_id, image_path, image_hash))

  def is_image_in_case(self, image_id, case):
    """Check if an image is attached to a case.

    Args:
      image_id: Image identifier
      case: Case name

    Returns:
      True if the image is attached to the case, otherwise False.
    """
    image_case = self._query_single_row((
        'SELECT 1 from image_case '
        'WHERE image_id = \'{0:s}\' AND case_id = \'{1:s}\'').format(
            image_id, case))
    if image_case:
      return True
    else:
      return False

  def link_image_to_case(self, image_id, case):
    """Attaches an image to a case.

    Args:
      image_id: Image identifier
      case: Case name
    """
    self._execute((
        'INSERT INTO image_case (case_id, image_id) '
        'VALUES (\'{0:s}\', \'{1:s}\')').format(case, image_id))

  def switch_database(
      self, host='127.0.0.1', port=5432, db_name='dfdewey', autocommit=False):
    """Connects to a different database.

    Args:
      host: Hostname or IP address of the PostgreSQL server
      port: Port of the PostgreSQL server
      db_name: Name of the database to connect to
      autocommit: Flag to set up the database connection as autocommit
    """
    self.db.commit()
    self.db.close()
    self.db = psycopg2.connect(
        database=db_name, user='dfdewey', password='password', host=host,
        port=port)
    if autocommit:
      self.db.set_isolation_level(
          psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    self.cursor = self.db.cursor()

  def table_exists(self, table_name, table_schema='public'):
    """Check if a table exists in the database.

    Args:
      table_name: Name of the table
      table_schema: Table schema if different from 'public'

    Returns:
      True if the table already exists, otherwise False
    """
    self.cursor.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = '{0:s}' AND table_name = '{1:s}'""".format(
            table_schema, table_name))

    return self.cursor.fetchone() is not None

  def unlink_image_from_case(self, image_id, case):
    """Removes an image from a case.

    Args:
      image_id: Image identifier
      case: Case name
    """
    self._execute(
        """
        DELETE FROM image_case
        WHERE case_id = '{0:s}' AND image_id = '{1:s}'""".format(
            case, image_id))

  def value_exists(self, table_name, column_name, value):
    """Check if a value exists in a table.

    Args:
      table_name: Name of the table
      column_name: Name of the column
      value: Value to query for

    Returns:
      True if the value exists, otherwise False
    """
    self.cursor.execute(
        """
        SELECT 1 from {0:s}
        WHERE {1:s} = '{2:s}'""".format(table_name, column_name, value))

    return self.cursor.fetchone() is not None
