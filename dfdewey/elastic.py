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
"""Elasticsearch datastore."""

import codecs
import collections
import logging
import uuid

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConnectionError
import six

# Setup logging
es_logger = logging.getLogger('elasticsearch')
es_logger.addHandler(logging.NullHandler())
es_logger.setLevel(logging.WARNING)


class ElasticsearchDataStore(object):
  """Implements the datastore."""

  # Number of events to queue up when bulk inserting events.
  DEFAULT_FLUSH_INTERVAL = 1000
  DEFAULT_SIZE = 100
  DEFAULT_LIMIT = DEFAULT_SIZE  # Max events to return
  DEFAULT_FROM = 0
  DEFAULT_STREAM_LIMIT = 5000  # Max events to return when streaming results

  def __init__(self, host='127.0.0.1', port=9200):
    """Create an Elasticsearch client."""
    super(ElasticsearchDataStore, self).__init__()
    self.client = Elasticsearch([{'host': host, 'port': port}])
    self.import_counter = collections.Counter()
    self.import_events = []

  def create_index(self, index_name=uuid.uuid4().hex, doc_type='string'):
    """Create index with Timesketch settings.

    Args:
        index_name: Name of the index. Default is a generated UUID.
        doc_type: Name of the document type. Default id generic_event.

    Returns:
        Index name in string format.
        Document type in string format.
    """

    if not self.client.indices.exists(index_name):
      try:
        self.client.indices.create(index=index_name)
      except ConnectionError:
        raise RuntimeError('Unable to connect to backend datastore.')

    if not isinstance(index_name, six.text_type):
      index_name = codecs.decode(index_name, 'utf8')
    if not isinstance(doc_type, six.text_type):
      doc_type = codecs.decode(doc_type, 'utf8')

    return index_name, doc_type

  def delete_index(self, index_name):
    """Delete Elasticsearch index.

    Args:
        index_name: Name of the index to delete.
    """
    if self.client.indices.exists(index_name):
      try:
        self.client.indices.delete(index=index_name)
      except ConnectionError as e:
        raise RuntimeError(
            'Unable to connect to backend datastore: {}'.format(e)
        )

  def import_event(
      self, index_name, event_type, event=None,
      event_id=None, flush_interval=DEFAULT_FLUSH_INTERVAL):
    """Add event to Elasticsearch.

    Args:
        index_name: Name of the index in Elasticsearch
        event_type: Type of event (e.g. plaso_event)
        event: Event dictionary
        event_id: Event Elasticsearch ID
        flush_interval: Number of events to queue up before indexing

    Returns:
        The number of events processed.
    """
    if event:
      for k, v in event.items():
        if not isinstance(k, six.text_type):
          k = codecs.decode(k, 'utf8')

        # Make sure we have decoded strings in the event dict.
        if isinstance(v, six.binary_type):
          v = codecs.decode(v, 'utf8')

        event[k] = v

      # Header needed by Elasticsearch when bulk inserting.
      header = {
          'index': {
              '_index': index_name,
              '_type': event_type
          }
      }
      update_header = {
          'update': {
              '_index': index_name,
              '_type': event_type,
              '_id': event_id
          }
      }

      if event_id:
        # Event has "lang" defined if there is a script used for import.
        if event.get('lang'):
          event = {'script': event}
        else:
          event = {'doc': event}
        header = update_header

      self.import_events.append(header)
      self.import_events.append(event)
      self.import_counter['events'] += 1

      if self.import_counter['events'] % int(flush_interval) == 0:
        self.client.bulk(body=self.import_events)
        self.import_events = []
    else:
      # Import the remaining events in the queue.
      if self.import_events:
        self.client.bulk(body=self.import_events)

    return self.import_counter['events']
