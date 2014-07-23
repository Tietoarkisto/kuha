import unittest
from datetime import datetime
import logging

import mock

from ..util import LogCapture
from ...exception import HarvestError
from ...importer import harvest

def make_item(identifier):
    item = mock.Mock()
    item.identifier = identifier
    return item


def make_format(prefix):
    format_ = mock.Mock()
    format_.prefix = prefix
    return format_


class TestUpdateFormats(unittest.TestCase):

    def test_successful_update(self):
        formats = {
            'oai_dc': (
                'http://www.openarchives.org/OAI/2.0/oai_dc/',
                u'http://www.openarchives.org/OAI/2.0/oai_dc.xsd',
            ),
            u'ddi': (
                'http://www.icpsr.umich.edu/DDI/Version2-0',
                'http://www.icpsr.umich.edu/DDI/Version2-0.dtd',
            ),
        }

        oai_dc_mock = make_format(u'oai_dc')
        ead_mock = make_format(u'ead')

        provider = mock.Mock()
        provider.formats.return_value = formats

        with LogCapture(harvest) as log:
            with mock.patch.object(harvest, 'models') as models:
                models.Format.list.return_value = [oai_dc_mock, ead_mock]
                harvest.update_formats(provider, purge=True)

        self.assertEqual(oai_dc_mock.mark_as_deleted.mock_calls, [])
        ead_mock.mark_as_deleted.assert_called_once_with()
        models.Format.list.assert_called_once_with(ignore_deleted=True)
        self.assertItemsEqual(
            models.Format.create_or_update.mock_calls,
            [mock.call(p, n, s) for p, (n, s) in formats.iteritems()]
        )
        models.purge_deleted.assert_called_once_with()
        provider.formats.assert_called_once_with()
        models.commit.assert_called_once_with()

        log.assert_emitted('Removed 1 format and added 1 format.')

    def test_no_formats(self):
        provider = mock.Mock()
        provider.formats.return_value = {}
        with self.assertRaises(HarvestError) as cm:
            harvest.update_formats(provider)
        self.assertIn('no formats', cm.exception.message)

    def test_provider_fails(self):
        provider = mock.Mock()
        provider.formats.side_effect = ImportError('some message')

        with LogCapture(harvest) as log:
            with self.assertRaises(HarvestError) as cm:
                harvest.update_formats(provider)

        self.assertIn('some message', cm.exception.message)
        log.assert_emitted('Failed to update metadata formats')

    def test_invalid_format(self):
        provider = mock.Mock()
        provider.formats.return_value = {'prefix': 'invalid'}
        self.assertRaises(HarvestError, harvest.update_formats, provider)


class TestUpdateItems(unittest.TestCase):

    def test_successful_update(self):
        provider = mock.Mock()
        provider.identifiers.return_value = ['asd', u'U', 'a:b']
        item_mocks = [make_item(u'1234'), make_item(u'asd')]

        with LogCapture(harvest) as log:
            with mock.patch.object(harvest, 'models') as models:
                models.Item.list.return_value = item_mocks
                harvest.update_items(provider, purge=True)

        provider.identifiers.assert_called_once_with()
        item_mocks[0].mark_as_deleted.assert_called_once_with()
        self.assertEqual(item_mocks[1].mark_as_deleted.mock_calls, [])
        self.assertItemsEqual(
            models.Item.create_or_update.mock_calls,
            [mock.call(i) for i in ['asd', u'U', 'a:b']]
        )
        models.purge_deleted.assert_called_once_with()
        models.commit.assert_called_once_with()
        log.assert_emitted('Removed 1 item and added 2 items.')

    def test_no_identifiers(self):
        provider = mock.Mock()
        provider.identifiers.return_value = []
        item_mock = make_item(u'id')

        with mock.patch.object(harvest, 'models') as models:
            models.Item.list.return_value = [item_mock]
            harvest.update_items(provider, purge=False)
        item_mock.mark_as_deleted.assert_called_once_with()

    def test_provider_fails(self):
        provider = mock.Mock()
        provider.identifiers.side_effect = ValueError('abcabc')

        with self.assertRaises(HarvestError) as cm:
            harvest.update_items(provider)
        self.assertIn('abcabc', cm.exception.message)

    def test_duplicate_identifiers(self):
        provider = mock.Mock()
        provider.identifiers.return_value = [
            'i2', 'i1', 'i3', 'i1', 'i1', 'i2',
        ]

        with mock.patch.object(harvest, 'models') as models:
            models.Item.list.return_value = []
            harvest.update_items(provider, purge=False)
        self.assertItemsEqual(
            models.Item.create_or_update.mock_calls,
            [mock.call(i) for i in ['i1', 'i2', 'i3']]
        )

    def test_invalid_identifiers(self):
        class InvalidId(object):
            def __unicode__(self):
                raise TypeError('conversion failed')
        provider = mock.Mock()
        provider.identifiers.return_value = [
            'ok', InvalidId(), 'oai:1234',
        ]

        with mock.patch.object(harvest, 'models') as models:
            models.Item.list.return_value = []
            with self.assertRaises(HarvestError) as cm:
                harvest.update_items(provider)
        self.assertIn('conversion failed', cm.exception.message)


class TestUpdateRecords(unittest.TestCase):

    def test_successful_harvest(self):
        formats = map(make_format, [u'ead', u'oai_dc'])
        identifiers = [make_item(u'item{0}'.format(i)) for i in xrange(4)]
        time = datetime(2014, 2, 4, 10, 54, 27)

        provider = mock.Mock()
        provider.get_record.return_value = '<xml ... />'
        provider.has_changed.side_effect = (
            lambda identifier, _: identifier != u'item2'
        )

        with LogCapture(harvest) as log:
            with mock.patch.object(harvest, 'models') as models:
                with mock.patch.object(harvest, 'update_sets') as (
                        update_sets_mock):
                    models.Format.list.return_value = formats
                    models.Item.list.return_value = identifiers
                    harvest.update_records(provider, time)

        self.assertItemsEqual(
            provider.get_record.mock_calls,
            [mock.call(id_, prefix)
             for id_ in [u'item0', u'item1', u'item3']
             for prefix in [u'ead', u'oai_dc']]
        )
        self.assertItemsEqual(
            update_sets_mock.mock_calls,
            [mock.call(provider, id_)
             for id_ in [u'item0', u'item1', u'item3']],
        )
        self.assertItemsEqual(
            models.Record.create_or_update.mock_calls,
            [mock.call(id_, prefix, '<xml ... />')
             for id_ in [u'item0', u'item1', u'item3']
             for prefix in [u'ead', u'oai_dc']]
        )
        self.assertEqual(
            models.commit.mock_calls,
            [mock.call() for _ in xrange(6)]
        )
        log.assert_emitted('Skipping item "item2"')
        log.assert_emitted('Updated 6 records.')

    def test_no_time(self):
        formats = [make_format(u'oai_dc')]
        items = [make_item(u'oai:test:id')]
        provider = mock.Mock()
        provider.get_record.return_value = '<oai_dc:dc>...</oai_dc:dc>'

        with mock.patch.object(harvest, 'update_sets'):
            with mock.patch.object(harvest, 'models') as models:
                models.Format.list.return_value = formats
                models.Item.list.return_value = items
                harvest.update_records(provider, since=None)

        self.assertEqual(provider.has_changed.mock_calls, [])
        provider.get_record.assert_called_once_with(
            u'oai:test:id', u'oai_dc')

    def test_no_records(self):
        provider = mock.Mock()
        time = datetime(2014, 2, 4, 10, 54, 27)
        with mock.patch.object(harvest, 'models') as models:
            models.Item.list.return_value = []
            models.Format.list.return_value = [make_format(u'ead')]
            harvest.update_records(provider, since=time)
        self.assertEqual(provider.has_changed.mock_calls, [])
        self.assertEqual(provider.get_record.mock_calls, [])
        self.assertEqual(models.commit.mock_calls, [])

    def test_harvest_fails(self):
        items = map(make_item, ['id1', 'id2'])
        formats = [make_format(u'ead')]
        xml = 'data'

        def get_record(id_, prefix):
            if id_ == 'id1':
                raise ValueError('crosswalk error')
            else:
                return xml
        provider = mock.Mock()
        provider.get_record.side_effect = get_record

        with mock.patch.object(harvest, 'update_sets'):
            with mock.patch.object(harvest, 'models') as models:
                models.Item.list.return_value = items
                models.Format.list.return_value = formats
                with LogCapture(harvest) as log:
                    harvest.update_records(provider)

        models.Record.create_or_update.assert_called_once_with(
            'id2', 'ead', xml)
        log.assert_emitted(
            'Failed to disseminate format "ead" for item "id1"')
        log.assert_emitted('crosswalk error')

    def test_deleted_record(self):
        formats = [make_format(u'oai_dc')]
        items = [make_item(u'some_item')]
        provider = mock.Mock()
        provider.get_record.return_value = None

        with mock.patch.object(harvest, 'update_sets'):
            with mock.patch.object(harvest, 'models') as models:
                models.Format.list.return_value = formats
                models.Item.list.return_value = items
                harvest.update_records(provider, since=None)

        models.Record.mark_as_deleted.assert_called_once_with(
            u'some_item', u'oai_dc',
        )

    def test_update_sets_fails(self):
        formats = [make_format(u'oai_dc')]
        items = map(make_item, [u'item1', u'item2'])

        provider = mock.Mock()
        provider.get_record.return_value = '<oai_dc:dc>...</oai_dc:dc>'

        with mock.patch.object(harvest, 'update_sets') as (
                update_sets_mock):
            update_sets_mock.side_effect = ValueError('invalid set spec')
            with mock.patch.object(harvest, 'models') as models:
                models.Item.list.return_value = items
                models.Format.list.return_value = formats
                with LogCapture(harvest) as log:
                    harvest.update_records(provider)

        self.assertItemsEqual(
            update_sets_mock.mock_calls,
            [mock.call(provider, id_) for id_ in [u'item1', u'item2']],
        )
        log.assert_emitted('Failed to update item "item1"')
        log.assert_emitted('Failed to update item "item2"')
        log.assert_emitted('invalid set spec')

    def test_delete_single_record(self):
        formats = map(make_format, [u'oai_dc', u'ead', u'ddi'])
        items = [make_item(u'pelle')]
        def get_record(id_, prefix):
            if prefix == u'oai_dc':
                raise ValueError('invalid data')
            elif prefix == u'ead':
                return None
            elif prefix == u'ddi':
                return 'data'
        provider = mock.Mock()
        provider.get_record.side_effect = get_record
        provider.get_sets.return_value = []

        with mock.patch.object(harvest, 'models') as models:
            models.Format.list.return_value = formats
            models.Item.list.return_value = items
            harvest.update_records(provider, since=None)

        models.Record.mark_as_deleted.assert_called_once_with(
            u'pelle', u'ead')
        models.Record.create_or_update.assert_called_once_with(
            u'pelle', u'ddi', 'data')


class TestUpdateSets(unittest.TestCase):

    def test_valid_sets(self):
        provider = mock.Mock()
        provider.get_sets.return_value = [
            (u'a:b', 'Set B'),
            ('a',   u'Set A'),
            ('a:b:c','Set C'),
        ]

        with mock.patch.object(harvest, 'models') as models:
            harvest.update_sets(provider, 'oai:example.org:item')

        models.Item.get.assert_called_once_with('oai:example.org:item')
        item = models.Item.get.return_value
        item.clear_sets.assert_called_once_with()
        self.assertEqual(
            models.Set.create_or_update.mock_calls,
            [mock.call('a', u'Set A'),
             mock.call(u'a:b', 'Set B'),
             mock.call('a:b:c', 'Set C')]
        )
        set_ = models.Set.create_or_update.return_value
        self.assertEqual(
            item.add_to_set.mock_calls,
            [mock.call(set_) for _ in xrange(3)]
        )

    def test_no_sets(self):
        provider = mock.Mock()
        provider.get_sets.return_value = []
        with mock.patch.object(harvest, 'models') as models:
            harvest.update_sets(provider, 'item')
        item = models.Item.get.return_value
        item.clear_sets.assert_called_once_with()
        self.assertEqual(item.add_to_set.mock_calls, [])
