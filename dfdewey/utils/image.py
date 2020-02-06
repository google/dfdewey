# Copyright 2019 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Image File Access Functions."""

import hashlib

import psycopg2
from psycopg2 import extras
import pytsk3


def list_directory(
    c, directory, part=None, stack=None, rows=None, batch_size=1500):
  """Recursive function to create a filesystem listing.

  Args:
      c: sqlite database cursor
      directory: pytsk directory object
      part: partition number
      stack: Inode stack to control recursive filesystem parsing
      rows: Array for batch database inserts
      batch_size: number of rows to insert at a time

  Returns:
      Current rows array for recursion
  """
  if not stack:
    stack = []
  if not rows:
    rows = []
  stack.append(directory.info.fs_file.meta.addr)

  for directory_entry in directory:
    if (not hasattr(directory_entry, 'info') or
        not hasattr(directory_entry.info, 'name') or
        not hasattr(directory_entry.info.name, 'name') or
        directory_entry.info.meta is None or
        directory_entry.info.name.name in [b'.', b'..'] or
        directory_entry.info.name.flags == pytsk3.TSK_FS_NAME_FLAG_UNALLOC):
      continue
    try:
      name = directory_entry.info.name.name.decode('utf-8')
    except UnicodeDecodeError:
      print('Unable to decode: {}'.format(directory_entry.info.name.name))
      continue
    if part:
      rows.append((directory_entry.info.meta.addr,
                   name.replace('\'', '\'\''),
                   part,))
      if len(rows) >= batch_size:
        extras.execute_values(
            c,
            'INSERT INTO files (inum, filename, part) VALUES %s',
            rows)
        rows = []
    else:
      rows.append((directory_entry.info.meta.addr,
                   name.replace('\'', '\'\''),))
      if len(rows) >= batch_size:
        extras.execute_values(
            c,
            'INSERT INTO files (inum, filename) VALUES %s',
            rows)
        rows = []

    try:
      sub_directory = directory_entry.as_directory()
      inode = directory_entry.info.meta.addr

      if inode not in stack:
        rows = list_directory(
            c,
            sub_directory,
            part=part,
            stack=stack,
            rows=rows,
            batch_size=batch_size)

    except IOError:
      pass

  stack.pop(-1)
  if not stack:
    if part:
      extras.execute_values(
          c,
          'INSERT INTO files (inum, filename, part) VALUES %s',
          rows)
    else:
      extras.execute_values(
          c,
          'INSERT INTO files (inum, filename) VALUES %s',
          rows)
  return rows


def initialise_block_db(image_path):
  """Creates a new image database.

  Args:
      image_path: path to image file
  """
  img = pytsk3.Img_Info(image_path)

  db_name = ''.join(
      ('fs', hashlib.md5(image_path.encode('utf-8')).hexdigest()))
  inum_db = psycopg2.connect(
      user='dfdewey',
      password='password',
      host='127.0.0.1',
      port=5432)
  inum_db.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
  c = inum_db.cursor()

  c.execute('CREATE DATABASE {0:s}'.format(db_name))
  inum_db.close()

  inum_db = psycopg2.connect(
      database=db_name,
      user='dfdewey',
      password='password',
      host='127.0.0.1',
      port=5432)
  c = inum_db.cursor()

  populate_block_db(img, c, batch_size=1500)

  inum_db.commit()
  inum_db.close()


def populate_block_db(img, c, batch_size=1500):
  """Creates a new image database.

  Args:
      img: pytsk image info object
      c: sqlite database cursor
      batch_size: number of rows to insert at a time
  """
  print('Image database does not already exist. Parsing image filesystem(s)...')
  print('Batch size: {0:d}'.format(batch_size))
  c.execute('CREATE TABLE blocks (block INTEGER, inum INTEGER, part INTEGER)')
  c.execute('CREATE TABLE files (inum INTEGER, filename TEXT, part INTEGER)')

  has_partition_table = False
  try:
    volume = pytsk3.Volume_Info(img)
    if volume:
      print('Image has a partition table...')
      has_partition_table = True
    rows = []
    for part in volume:
      print('Parsing partition {0:d}: {1:s}'.format(
          part.addr, part.desc.decode('utf-8')))
      if part.flags != pytsk3.TSK_VS_PART_FLAG_ALLOC:
        continue
      fs = pytsk3.FS_Info(img, offset=part.start * 512)
      for i in range(fs.info.first_inum, fs.info.last_inum + 1):
        f = fs.open_meta(i)
        if f.info.meta.nlink > 0:
          for attr in f:
            for run in attr:
              for j in range(run.len):
                rows.append((run.addr + j, i, part.addr,))
                if len(rows) >= batch_size:
                  extras.execute_values(
                      c,
                      'INSERT INTO blocks (block, inum, part) VALUES %s',
                      rows)
                  rows = []
      if rows:
        extras.execute_values(
            c,
            'INSERT INTO blocks (block, inum, part) VALUES %s',
            rows)

      # File names
      directory = fs.open_dir(path='/')
      list_directory(c, directory, part=part.addr, batch_size=batch_size)
  except IOError:
    pass

  if not has_partition_table:
    fs = pytsk3.FS_Info(img)
    rows = []
    for i in range(fs.info.first_inum, fs.info.last_inum + 1):
      f = fs.open_meta(i)
      if f.info.meta.nlink > 0:
        for attr in f:
          for run in attr:
            for j in range(run.len):
              rows.append((run.addr + j, i,))
              if len(rows) >= batch_size:
                extras.execute_values(
                    c,
                    'INSERT INTO blocks (block, inum) VALUES %s',
                    rows)
                rows = []
      if rows:
        extras.execute_values(
            c,
            'INSERT INTO blocks (block, inum) VALUES %s',
            rows)

    # File names
    directory = fs.open_dir(path='/')
    list_directory(c, directory, batch_size=batch_size)

  c.execute('CREATE INDEX blocks_index ON blocks (block, part);')
  c.execute('CREATE INDEX files_index ON files (inum, part);')


def get_inums(c, block, part=None):
  """Gets inode number from block offset.

  Args:
      c: sqlite database cursor
      block: Block offset within the image
      part: Partition number

  Returns:
      Inode number(s) of the given block or None
  """
  if part:
    c.execute('SELECT inum FROM blocks '
              'WHERE block = {0:d} '
              'AND part = {1:d}'.format(int(block), part))
  else:
    c.execute('SELECT inum FROM blocks WHERE block = {0:d}'.format(int(block)))
  inums = c.fetchall()

  return inums


def get_filename(c, inum, part=None):
  """Gets filename given an inode number.

  Args:
      c: sqlite database cursor
      inum: Inode number of target file
      part: Partition number

  Returns:
      Filename of given inode or None
  """
  if part:
    c.execute('SELECT filename FROM files '
              'WHERE inum = {0:d} '
              'AND part = {1:d}'.format(inum, part))
  else:
    c.execute('SELECT filename FROM files WHERE inum = {0:d}'.format(inum))
  filenames = c.fetchall()
  if filenames:
    filename = filenames[0][0]
  else:
    filename = '*None*'

  return filename


def get_resident_inum(offset, fs):
  """Gets filename given an inode number.

  Args:
      offset: data offset within volume
      fs: pytsk3 FS_INFO object

  Returns:
      inode number of resident data
  """
  block_size = fs.info.block_size
  block = int(offset / block_size)

  f = fs.open_meta(0)
  mft_entry = 0
  for attr in f:
    for run in attr:
      for j in range(run.len):
        if run.addr + j == block:
          mft_entry += int((offset - (block * block_size)) / 1024)
          return mft_entry
        else:
          mft_entry += int(block_size / 1024)
  return 0


def get_filename_from_offset(image_file, offset):
  """Gets filename given a byte offset within an image.

  Args:
      image_file: Source image filename
      offset: Byte offset within the image

  Returns:
      Filename allocated the given offset
  """
  sector_offset = offset / 512
  img = pytsk3.Img_Info(image_file)

  db_name = ''.join(
      ('fs', hashlib.md5(image_file.encode('utf-8')).hexdigest()))
  inum_db = psycopg2.connect(
      user='dfdewey',
      password='password',
      host='127.0.0.1',
      port=5432)
  inum_db.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
  c = inum_db.cursor()
  c.execute(
      'SELECT 1 FROM pg_catalog.pg_database '
      'WHERE datname = \'{0:s}\''.format(db_name))
  db_exists = c.fetchone()
  if not db_exists:
    c.execute('CREATE DATABASE {0:s}'.format(db_name))
    inum_db.close()

    inum_db = psycopg2.connect(
        database=db_name,
        user='dfdewey',
        password='password',
        host='127.0.0.1',
        port=5432)
    c = inum_db.cursor()

    populate_block_db(img, c)
  else:
    inum_db.close()

    inum_db = psycopg2.connect(
        database=db_name,
        user='dfdewey',
        password='password',
        host='127.0.0.1',
        port=5432)
    c = inum_db.cursor()

  partition = None
  partition_offset = None
  unalloc_part = False
  try:
    volume = pytsk3.Volume_Info(img)
    for part in volume:
      if part.start <= sector_offset < part.start + part.len:
        if part.flags != pytsk3.TSK_VS_PART_FLAG_ALLOC:
          unalloc_part = True
        partition = part.addr
        partition_offset = part.start
  except IOError:
    pass

  if not unalloc_part:
    try:
      if not partition_offset:
        fs = pytsk3.FS_Info(img)
      else:
        offset -= partition_offset * 512
        fs = pytsk3.FS_Info(img, offset=partition_offset * 512)
    except TypeError as e:
      print(e)
    block_size = fs.info.block_size

    inums = get_inums(c, offset / block_size, part=partition)

  filenames = None
  for i in inums:
    real_inum = i[0]
    if i[0] == 0 and fs.info.ftype == pytsk3.TSK_FS_TYPE_NTFS_DETECT:
      real_inum = get_resident_inum(offset, fs)
    filename = get_filename(c, real_inum, part=partition)
    if filename and not filenames:
      filenames = '{0:s} ({1:d})'.format(filename, real_inum)
    else:
      filenames = ' | '.join(
          (filenames, '{0:s} ({1:d})'.format(filename, real_inum)))

  inum_db.commit()
  inum_db.close()

  if filenames is None:
    return '*None*'
  else:
    return filenames
