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
"""Image File Access Functions."""

from datastore.postgresql import PostgresqlDataStore
import pytsk3


def initialise_block_db(image_path, image_hash, case):
  """Creates a new image database.

  Args:
    image_path: Path to image file
    image_hash: MD5 of the image
    case: Case ID

  Returns:
    Boolean value to indicate whether the image has already been processed
  """
  img = pytsk3.Img_Info(image_path)

  block_db = PostgresqlDataStore(autocommit=True)
  image_exists = check_tracking_database(block_db, image_path, image_hash, case)

  if not image_exists:
    db_name = ''.join(('fs', image_hash))
    block_db.execute('CREATE DATABASE {0:s}'.format(db_name))

    block_db.switch_database(db_name=db_name)

    populate_block_db(img, block_db, batch_size=1500)

  return image_exists


def check_tracking_database(tracking_db, image_path, image_hash, case):
  """Checks if an image exists in the tracking database.

  Checks if an image exists in the tracking database and adds it if not.
  If the image exists, but is not associated with the given case ID, will add
  the association.

  Args:
    tracking_db: PostgreSQL database
    image_path: Path to image file
    image_hash: MD5 of the image
    case: Case ID

  Returns:
    Boolean value to indicate the existence of the image
  """
  tables_exist = tracking_db.table_exists('images')

  image_exists = False
  if not tables_exist:
    tracking_db.execute(
        'CREATE TABLE images (image_path TEXT, image_hash TEXT PRIMARY KEY)')

    tracking_db.execute("""
        CREATE TABLE image_case (
          case_id TEXT, image_hash TEXT REFERENCES images(image_hash), 
          PRIMARY KEY (case_id, image_hash))""")
  else:
    image_exists = tracking_db.value_exists('images', 'image_hash', image_hash)

  image_case_exists = False
  if image_exists:
    image_case = tracking_db.query_single_row("""
        SELECT 1 from image_case
        WHERE image_hash = '{0:s}' AND case_id = '{1:s}'""".format(
            image_hash, case))
    if image_case:
      image_case_exists = True

  if not image_exists:
    tracking_db.execute("""
        INSERT INTO images (image_path, image_hash)
        VALUES ('{0:s}', '{1:s}')""".format(image_path, image_hash))
  if not image_case_exists:
    tracking_db.execute("""
        INSERT INTO image_case (case_id, image_hash)
        VALUES ('{0:s}', '{1:s}')""".format(case, image_hash))

  return image_exists


def populate_block_db(img, block_db, batch_size=1500):
  """Creates a new image block database.

  Args:
    img: pytsk image info object
    block_db: PostgreSQL database
    batch_size: Number of rows to insert at a time
  """
  print('Image database does not already exist. Parsing image filesystem(s)...')
  block_db.execute(
      'CREATE TABLE blocks (block INTEGER, inum INTEGER, part INTEGER)')
  block_db.execute(
      'CREATE TABLE files (inum INTEGER, filename TEXT, part INTEGER)')

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
      fs = pytsk3.FS_Info(img, offset=part.start * volume.info.block_size)
      for i in range(fs.info.first_inum, fs.info.last_inum + 1):
        f = fs.open_meta(i)
        if f.info.meta.nlink > 0:
          for attr in f:
            for run in attr:
              for j in range(run.len):
                rows.append((run.addr + j, i, part.addr,))
                if len(rows) >= batch_size:
                  block_db.bulk_insert('blocks (block, inum, part)', rows)
                  rows = []
      if rows:
        block_db.bulk_insert('blocks (block, inum, part)', rows)

      # File names
      directory = fs.open_dir(path='/')
      list_directory(block_db, directory, part=part.addr, batch_size=batch_size)
  except IOError:
    pass

  if not has_partition_table:
    fs = pytsk3.FS_Info(img)
    rows = []
    for i in range(fs.info.first_inum, fs.info.last_inum + 1):
      try:
        f = fs.open_meta(i)
        if f.info.meta.nlink > 0:
          for attr in f:
            for run in attr:
              for j in range(run.len):
                rows.append((run.addr + j, i,))
                if len(rows) >= batch_size:
                  block_db.bulk_insert('blocks (block, inum)', rows)
                  rows = []
        if rows:
          block_db.bulk_insert('blocks (block, inum)', rows)
      except OSError:
        continue

    # File names
    directory = fs.open_dir(path='/')
    list_directory(block_db, directory, batch_size=batch_size)

  block_db.execute('CREATE INDEX blocks_index ON blocks (block, part);')
  block_db.execute('CREATE INDEX files_index ON files (inum, part);')


def list_directory(
    block_db, directory, part=None, stack=None, rows=None, batch_size=1500):
  """Recursive function to create a filesystem listing.

  Args:
    block_db: PostgreSQL database
    directory: pytsk directory object
    part: Partition number
    stack: Inode stack to control recursive filesystem parsing
    rows: Array for batch database inserts
    batch_size: Number of rows to insert at a time

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
        block_db.bulk_insert('files (inum, filename, part)', rows)
        rows = []
    else:
      rows.append((directory_entry.info.meta.addr,
                   name.replace('\'', '\'\''),))
      if len(rows) >= batch_size:
        block_db.bulk_insert('files (inum, filename)', rows)
        rows = []

    try:
      sub_directory = directory_entry.as_directory()
      inode = directory_entry.info.meta.addr

      if inode not in stack:
        rows = list_directory(
            block_db,
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
      block_db.bulk_insert('files (inum, filename, part)', rows)
    else:
      block_db.bulk_insert('files (inum, filename)', rows)

  return rows


def get_filename_from_offset(image_path, image_hash, offset):
  """Gets filename given a byte offset within an image.

  Args:
    image_path: Source image path
    image_hash: Source image hash
    offset: Byte offset within the image

  Returns:
    Filename allocated to the given offset
  """
  img = pytsk3.Img_Info(image_path)

  db_name = ''.join(('fs', image_hash))
  block_db = PostgresqlDataStore(db_name=db_name)

  device_block_size = None
  partition = None
  partition_offset = None
  unalloc_part = False
  try:
    volume = pytsk3.Volume_Info(img)
    device_block_size = volume.info.block_size
    sector_offset = offset / device_block_size
    for part in volume:
      if part.start <= sector_offset < part.start + part.len:
        if part.flags != pytsk3.TSK_VS_PART_FLAG_ALLOC:
          unalloc_part = True
        partition = part.addr
        partition_offset = part.start
  except IOError:
    pass

  inums = None
  if not unalloc_part:
    try:
      if not partition_offset:
        fs = pytsk3.FS_Info(img)
      else:
        offset -= partition_offset * device_block_size
        fs = pytsk3.FS_Info(
            img, offset=partition_offset * device_block_size)
    except TypeError as e:
      print(e)
    block_size = fs.info.block_size

    inums = get_inums(block_db, offset / block_size, part=partition)

  filenames = []
  if inums:
    for i in inums:
      real_inum = i[0]
      if i[0] == 0 and fs.info.ftype == pytsk3.TSK_FS_TYPE_NTFS_DETECT:
        mft_record_size_offset = 0x40
        if partition_offset:
          mft_record_size_offset = \
              mft_record_size_offset + (partition_offset * device_block_size)
        mft_record_size = int.from_bytes(
            img.read(mft_record_size_offset, 1), 'little', signed=True)
        if mft_record_size < 0:
          mft_record_size = 2 ** (mft_record_size * -1)
        else:
          mft_record_size = mft_record_size * block_size
        real_inum = get_resident_inum(offset, fs, mft_record_size)
      filename = get_filename(block_db, real_inum, part=partition)
      if filename and not filenames:
        filenames.append('{0:s} ({1:d})'.format(filename, real_inum))
      else:
        if '{0:s} ({1:d})'.format(filename, real_inum) not in filenames:
          filenames.append('{0:s} ({1:d})'.format(filename, real_inum))

  if filenames is None:
    return '*None*'
  else:
    return ' | '.join(filenames)


def get_inums(block_db, block, part=None):
  """Gets inode number from block offset.

  Args:
    block_db: PostgreSQL database
    block: Block offset within the image
    part: Partition number

  Returns:
    Inode number(s) of the given block or None
  """
  if part:
    inums = block_db.query(
        'SELECT inum FROM blocks WHERE block = {0:d} AND part = {1:d}'.format(
            int(block), part))
  else:
    inums = block_db.query(
        'SELECT inum FROM blocks WHERE block = {0:d}'.format(int(block)))

  return inums


def get_resident_inum(offset, fs, mft_record_size):
  """Gets the inode number associated with NTFS $MFT resident data.

  Args:
    offset: Data offset within volume
    fs: pytsk3 FS_INFO object
    mft_record_size: Size of an $MFT entry

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
          mft_entry += int((offset - (block * block_size)) / mft_record_size)
          return mft_entry
        else:
          mft_entry += int(block_size / mft_record_size)
  return 0


def get_filename(block_db, inum, part=None):
  """Gets filename given an inode number.

  Args:
    block_db: PostgreSQL database
    inum: Inode number of target file
    part: Partition number

  Returns:
    Filename of given inode or None
  """
  if part:
    filenames = block_db.query(
        'SELECT filename FROM files WHERE inum = {0:d} AND part = {1:d}'.format(
            inum, part))
  else:
    filenames = block_db.query(
        'SELECT filename FROM files WHERE inum = {0:d}'.format(inum))

  if filenames:
    filename = filenames[0][0]
  else:
    filename = '*None*'

  return filename
