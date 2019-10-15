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
import os
import sys

import pytsk3
import sqlite3


def list_directory(c, directory, stack=None):
  """Recursive function to create a filesystem listing.

  Args:
      c: sqlite database cursor
      directory: pytsk directory object
      stack: Inode stack to control recursive filesystem parsing
  """
  if not stack:
    stack = []
  stack.append(directory.info.fs_file.meta.addr)

  for directory_entry in directory:
    if (not hasattr(directory_entry, 'info') or
        not hasattr(directory_entry.info, 'name') or
        not hasattr(directory_entry.info.name, 'name') or
        directory_entry.info.meta is None or
        directory_entry.info.name.name in [b'.', b'..']):
      continue
    c.execute('INSERT INTO files VALUES ({0:d}, "{1:s}")'.format(
        directory_entry.info.meta.addr,
        directory_entry.info.name.name.decode('utf-8')))

    try:
      sub_directory = directory_entry.as_directory()
      inode = directory_entry.info.meta.addr

      if inode not in stack:
        list_directory(c, sub_directory, stack=stack)

    except IOError:
      pass

  stack.pop(-1)


def populate_block_db(fs, c):
  """Creates a new image database.

  Args:
      fs: pytsk FS_Info object
      c: sqlite database cursor
  """
  print('Image database does not already exist. Parsing file system...')
  c.execute('CREATE TABLE blocks (block INTEGER, inum INTEGER)')

  for i in range(fs.info.last_inum + 1):
    f = fs.open_meta(i)
    for attr in f:
      for run in attr:
        for j in range(run.len):
          c.execute('INSERT INTO blocks VALUES ({0:d}, {1:d})'.format(
              run.addr + j, i))

  # File names
  c.execute('CREATE TABLE files (inum INTEGER, filename TEXT)')
  directory = fs.open_dir(path='/')
  list_directory(c, directory)


def get_inum(image_file, fs, block):
  """Gets inode number from block offset.

  Args:
      image_file: Source image filename
      fs: pytsk FS_Info object
      block: Block offset within the image

  Returns:
      Inode number of the given block or None
  """
  db_name = ''.join((
      '/tmp/',
      hashlib.md5(image_file.encode('utf-8')).hexdigest()))
  db_exists = os.path.exists(db_name)
  inum_db = sqlite3.connect(db_name)
  c = inum_db.cursor()
  if not db_exists:
    populate_block_db(fs, c)

  c.execute('SELECT inum FROM blocks WHERE block = {0:d}'.format(int(block)))
  inums = c.fetchall()
  if inums:
    inum = inums[0][0]
  else:
    inum = None
  inum_db.commit()
  inum_db.close()

  return inum


def get_filename(image_file, inum):
  """Gets filename given an inode number.

  Args:
      image_file: Source image filename
      inum: Inode number of target file

  Returns:
      Filename of given inode or None
  """
  db_name = ''.join((
      '/tmp/',
      hashlib.md5(image_file.encode('utf-8')).hexdigest()))
  inum_db = sqlite3.connect(db_name)
  c = inum_db.cursor()

  c.execute('SELECT filename FROM files WHERE inum = {0:d}'.format(inum))
  filenames = c.fetchall()
  if filenames:
    filename = filenames[0][0]
  else:
    filename = None

  inum_db.close()

  return filename


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

  partition_offset = None
  try:
    volume = pytsk3.Volume_Info(img)
    for part in volume:
      if part.start <= sector_offset < part.start + part.len:
        #print('Partition {0:d}: {1:s}'.format(
            #part.addr,
            #part.desc.decode('utf-8')))
        partition_offset = part.start
  except IOError:
    pass

  try:
    if not partition_offset:
      fs = pytsk3.FS_Info(img)
    else:
      offset -= partition_offset * 512
      fs = pytsk3.FS_Info(img, offset=partition_offset * 512)
  except TypeError as e:
    print(e)
  block_size = fs.info.block_size

  if (offset / block_size) > fs.info.last_block:
    print('Offset is larger than file system extents...')
    img.close()
    sys.exit(-1)

  if (offset / block_size) < fs.info.first_block:
    print('Offset is smaller than file system extents...')
    img.close()
    sys.exit(-1)

  inum = get_inum(image_file, fs, offset / block_size)
  filename = None
  if inum:
    filename = get_filename(image_file, inum)
  if filename is None:
    return '*None*'
  else:
    return filename
