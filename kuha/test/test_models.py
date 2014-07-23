# encoding: utf-8

import unittest
from datetime import datetime, timedelta

from lxml.etree import XMLSyntaxError
import sqlalchemy as sa
import sqlalchemy.exc as exc
import sqlalchemy.orm as orm
import mock

from ..util import datestamp_now
from .. import models
from ..models import (
    DBSession,
    Item, Record, Format, Datestamp, Set,
)


def make_format(prefix):
    if prefix == u'ead':
        return Format.create(
            prefix,
            u'urn:isbn:1-931666-22-9',
            u'http://www.loc.gov/ead/ead.xsd',
        )
    elif prefix == u'oai_dc':
        return Format.create(
            prefix,
            u'http://www.openarchives.org/OAI/2.0/oai_dc/',
            u'http://www.openarchives.org/OAI/2.0/oai_dc.xsd',
        )
    elif prefix == u'ddi':
        return Format.create(
            prefix,
            u'http://www.icpsr.umich.edu/DDI/Version2-0',
            u'http://www.icpsr.umich.edu/DDI/Version2-0.dtd',
        )


def make_xml(format_):
    return '''
        <test xmlns="{0}"
              xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
              xsi:schemaLocation="{0} {1}">
            <title>Test Record</title>
            <subject>software testing</subject>
        </test>
    '''.format(format_.namespace, format_.schema)


class ModelTestCase(unittest.TestCase):

    def setUp(self):
        # Dispose any existing database session.
        DBSession.remove()

        # in-memory database
        self.engine = sa.create_engine('sqlite://')

        # Wrap the test cases in a transaction.
        connection = self.engine.connect()
        self.transaction = connection.begin()
        DBSession.configure(
            bind=connection,
            # Disable the ZopeTransactionExtension.
            extension=[],
        )
        models._Base.metadata.bind = self.engine

        # Create tables.
        models._Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.transaction.rollback()
        DBSession.remove()


class TestCreateItem(ModelTestCase):

    def test_create(self):
        Item.create('oai:example.org:bla')
        i = DBSession.query(Item).filter_by(
            identifier='oai:example.org:bla').one()
        self.assertIs(i.deleted, False)

    def test_duplicate(self):
        with self.assertRaises(exc.IntegrityError):
            Item.create('asdasd')
            Item.create('asdasd')
            DBSession.flush()


class TestItemExists(ModelTestCase):

    def test_item_exists(self):
        Item.create('identifier')
        self.assertIs(Item.exists('identifier'), True)

    def test_item_not_exists(self):
        self.assertIs(Item.exists('identifier'), False)

    def test_item_deleted(self):
        Item.create('item1').deleted = True
        Item.create('item2')

        self.assertIs(Item.exists('item1', False), True)
        self.assertIs(Item.exists('item1', True), False)
        self.assertIs(Item.exists('item2', True), True)


class TestUpdateItems(ModelTestCase):

    def test_create_or_update(self):
        item = Item.create('some id')
        item.deleted = True
        i1 = Item.create_or_update('some id')
        i2 = Item.create_or_update('other id')

        self.assertIs(item, i1)
        self.assertIs(item.deleted, False)
        self.assertEqual(i2.identifier, 'other id')
        self.assertIs(i2.deleted, False)


class TestListItems(ModelTestCase):

    def test_list_deleted(self):
        i1 = Item.create('qwe')
        i2 = Item.create('rty')
        i2.deleted = True
        self.assertItemsEqual(Item.list(ignore_deleted=False), [i1, i2])
        self.assertItemsEqual(Item.list(ignore_deleted=True), [i1])

    def test_empty_list(self):
        self.assertEqual(Item.list(), [])


class TestMarkItemsAsDeleted(ModelTestCase):

    def test_mark_item(self):
        item = Item.create('hjkl')
        Datestamp.create(datetime(1970, 1, 1, 0, 0, 0))
        item.mark_as_deleted()
        self.assertIs(item.deleted, True)
        # Datestamp should not have changed since no records were deleted.
        self.assertEqual(Datestamp.get(), datetime(1970, 1, 1, 0, 0, 0))

    def test_mark_item_and_records(self):
        date = datetime(1970, 1, 1, 0, 0, 0)
        item = Item.create('hjkl')
        fmt1 = make_format('ead')
        fmt2 = make_format('oai_dc')
        r1 = Record.create('hjkl', 'ead', make_xml(fmt1))
        r2 = Record.create('hjkl', 'oai_dc', make_xml(fmt2))
        DBSession.query(Datestamp).one().datestamp = date

        item.mark_as_deleted()

        # The item and assocated records should have been marked as
        # deleted.
        self.assertIs(item.deleted, True)
        self.assertIs(r1.deleted, True)
        self.assertIs(r2.deleted, True)
        # Formats should not have been deleted.
        self.assertIs(fmt1.deleted, False)
        self.assertIs(fmt2.deleted, False)
        # Datestamp should have updated since records were deleted.
        self.assertTrue(Datestamp.get() > date)


class TestCreateFormat(ModelTestCase):

    def test_create(self):
        Format.create('ok', 'urn:xxxxx', 'x.xsd')
        f = DBSession.query(Format).filter_by(prefix='ok').one()
        self.assertIs(f.deleted, False)

    def test_invalid_prefix(self):
        with self.assertRaises(ValueError):
            Format.create('!@#$', 'urn:xxxxx', 'x.xsd')

    def test_duplicate(self):
        with self.assertRaises(exc.IntegrityError):
            Format.create('dup', 'urn:ns', 'schema.xsd')
            Format.create('dup', 'http://asd/', 'asd.xsd')
            DBSession.flush()


class TestFormatExists(ModelTestCase):

    def test_format_exists(self):
        Format.create('example',
                      'http://example.com/ns/',
                      'http://example.com/schema.xsd')
        self.assertIs(Format.exists('example'), True)

    def test_format_not_exists(self):
        self.assertIs(Format.exists('example'), False)

    def test_format_deleted(self):
        Format.create('a', 'urn:a', 'a.xsd').deleted = True
        Format.create('b', 'urn:b', 'b.xsd')

        self.assertIs(Format.exists('a', False), True)
        self.assertIs(Format.exists('a', True), False)
        self.assertIs(Format.exists('b', True), True)


class TestListFormats(ModelTestCase):

    def test_no_formats(self):
        self.assertEqual(Format.list(), [])

    def test_all_formats(self):
        f1 = Format('ex1', 'http://example.org/1', 'schema.xsd')
        f2 = Format('ex2', 'http://example.org/2', 'schema.xsd')
        f2.deleted = True
        f3 = Format('ex3', 'urn:ex3', 'ex3.xsd')
        DBSession.add_all([f1, f2, f3])

        self.assertItemsEqual(
            Format.list(ignore_deleted=False),
            [f1, f2, f3]
        )
        self.assertItemsEqual(
            Format.list(ignore_deleted=True),
            [f1, f3]
        )

    def test_formats_for_item(self):
        Item.create('identifier')
        f1 = Format.create('ex1', 'http://example1.com/ns/', 'schema1.xsd')
        f2 = Format.create('ex2', 'http://example2.com/ns/', 'schema2.xsd')
        Format.create('ex3', 'http://example3.com/ns/', 'schema3.xsd')
        Format.create('ex4', 'http://example4.com/ns/', 'schema4.xsd')
        Record.create('identifier', 'ex1', make_xml(f1))
        Record.create('identifier', 'ex2', make_xml(f2))
        r4 = Record.create('identifier', 'ex4', None)
        r4.deleted = True
        self.assertItemsEqual(Format.list('identifier', True), [f1, f2])

    def test_item_has_no_formats(self):
        Format.create('a', 'urn:a', 'a.xsd')
        self.assertEqual(Format.list('identifier'), [])


class TestUpdateFormats(ModelTestCase):

    def test_change_format(self):
        date = datetime(2014, 4, 24, 15, 11, 0)
        Item.create('id')
        f = make_format('ddi')
        r = Record.create('id', 'ddi', make_xml(f), date)
        DBSession.query(Datestamp).one().datestamp = date

        # redundant update
        f.update(u'http://www.icpsr.umich.edu/DDI/Version2-0',
                 u'http://www.icpsr.umich.edu/DDI/Version2-0.dtd')
        self.assertIs(r.deleted, False)
        self.assertEqual(r.datestamp, date)
        self.assertEqual(Datestamp.get(), date)

        # change namespace and schema
        f.update('urn:new_namespace', 'asd.xsd')
        self.assertIs(r.deleted, True)
        self.assertTrue(r.datestamp > date)
        self.assertTrue(Datestamp.get() > date)

    def test_create_or_update(self):
        orig = Format.create('a', 'urn:testa', 'a.xsd')

        f1 = Format.create_or_update(
            prefix='a',
            namespace='http://example.org/testa',
            schema='a.xsd',
        )
        f2 = Format.create_or_update(
            prefix='b',
            namespace='urn:testb',
            schema='b.xsd',
        )

        self.assertIs(f1, orig)
        self.assertEqual(f1.namespace, 'http://example.org/testa')
        self.assertItemsEqual(
            DBSession.query(Format.prefix).all(),
            [('a',), ('b',)]
        )


class TestMarkFormatAsDeleted(ModelTestCase):

    def test_mark_format_and_items(self):
        date = datetime(2014, 4, 24, 15, 11, 0)
        fmt = make_format('oai_dc')
        ead = make_format('ead')
        i1 = Item.create('id1')
        i2 = Item.create('id2')
        r1 = Record.create('id1', 'oai_dc', make_xml(fmt), date)
        r2 = Record.create('id2', 'oai_dc', make_xml(fmt), date)
        r3 = Record.create('id1', 'ead', make_xml(ead), date)
        DBSession.query(Datestamp).one().datestamp = date

        fmt.mark_as_deleted()

        # The format and records should have been deleted.
        for obj in [fmt, r1, r2]:
            self.assertIs(obj.deleted, True)
        # Items and unrelated objects should not have been deleted.
        for obj in [i1, i2, ead, r3]:
            self.assertIs(obj.deleted, False)
        # Datestamp should have changed.
        self.assertTrue(Datestamp.get() > date)


class TestCreateRecord(ModelTestCase):

    def test_valid_record(self):
        date = datetime(1990, 2, 3, 4, 5, 6)
        Datestamp.create(date)
        Item.create('id1')
        Item.create('id2')
        ead = make_format('ead')
        ddi = make_format('ddi')

        Record.create('id1', 'ead', make_xml(ead))
        Record.create('id1', 'ddi', make_xml(ddi))
        Record.create('id2', 'ead', make_xml(ead))
        Record.create('id2', 'ddi', make_xml(ddi))

        self.assertEqual(len(DBSession.query(Record).all()), 4)
        self.assertTrue(Datestamp.get() > date)

    def test_invalid_types(self):
        Item.create('id')
        f = make_format('oai_dc')
        for data in [('id', 'prefix'), [1, 2, 3, 4]]:
            with self.assertRaises(Exception):
                Record.create('id', 'oai_dc', data)

    def test_duplicate_record(self):
        Item.create('id')
        f = make_format('ead')
        with self.assertRaises(exc.IntegrityError):
            Record.create('id', 'ead', make_xml(f))
            Record.create('id', 'ead', make_xml(f))
            DBSession.flush()

    def test_ill_formed_xml(self):
        Item.create('oai:asd:id')
        make_format('oai_dc')
        with self.assertRaises(XMLSyntaxError):
            Record.create('oai:asd:id', 'oai_dc', '<test:dc><invalid xml/')

    def test_xml_root_in_wrong_namespace(self):
        Item.create('abcde')
        f = make_format(u'ddi')
        xml = make_xml(f)
        f.namespace = u'http://www.icpsr.umich.edu/DDI/wrong-namespace'

        with self.assertRaises(ValueError) as cm:
            Record.create(u'abcde', u'ddi', xml)
        self.assertIn('wrong xml namespace', cm.exception.message)

    def test_xml_without_schema(self):
        data = '''
            <test xmlns="urn:isbn:1-931666-22-9"
                  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                <title>Test Record Title</title>
            </test>
        '''
        Item.create(u'id')
        f = make_format(u'ead')
        with self.assertRaises(ValueError) as cm:
            Record.create(u'id', u'ead', data)
        self.assertIn('no schema location', cm.exception.message)

    def test_xml_wrong_schema(self):
        Item.create(u'id')
        f = make_format(u'oai_dc')
        xml = make_xml(f)
        f.schema = u'http://wrong.location/oai_dc.xsd'
        with self.assertRaises(ValueError) as cm:
            Record.create(u'id', u'oai_dc', xml)
        self.assertIn('wrong schema location', cm.exception.message)

    def test_non_existent_prefix(self):
        Item.create('a')
        with self.assertRaises(ValueError) as cm:
            Record.create_or_update('a', 'oai_dc', '<asd/>')
        self.assertIn('non-existent metadata prefix',
                      cm.exception.message)
        self.assertIn('oai_dc', cm.exception.message)

    def test_non_existent_identifier(self):
        f = Format.create('a', 'http://a', 'a.xsd')
        with self.assertRaises(ValueError) as cm:
            Record.create_or_update('item', 'a', make_xml(f))
        self.assertIn('non-existent identifier',
                      cm.exception.message)
        self.assertIn('item', cm.exception.message)


class TestListRecords(ModelTestCase):

    def setUp(self):
        ModelTestCase.setUp(self)

        # Create some test data.
        self.items = [
            Item.create('item{0}'.format(i)) for i in xrange(1, 4)
        ]
        formats = [
            Format.create(
                'fmt{0}'.format(i),
                'ns{0}'.format(i),
                'schema.xsd',
            )
            for i in xrange(1, 4)
        ]
        self.records = [
            Record.create('item1', 'fmt1', make_xml(formats[0]),
                          datetime(2013,3,19, 11,1,54)),
            Record.create('item1', 'fmt2', make_xml(formats[1]),
                          datetime(2014,2,22, 14,45,0)),
            Record.create('item2', 'fmt1', make_xml(formats[0]),
                          datetime(2014,1,4, 18,0,2)),
            Record.create('item3', 'fmt3', make_xml(formats[2]),
                          datetime(2013,3,19, 11,1,54)),
        ]
        self.records[3].deleted = True

    def test_get_all_records(self):
        self.assertItemsEqual(Record.list(), self.records)

    def test_get_records_by_format(self):
        self.assertItemsEqual(Record.list(metadata_prefix='invalid'), [])
        self.assertItemsEqual(
            Record.list(metadata_prefix='fmt1'),
            [self.records[0], self.records[2]]
        )

    def test_get_records_from_date(self):
        self.assertItemsEqual(
            Record.list(from_date=datetime(1970, 1, 1, 0, 0, 0)),
            self.records[0:4]
        )
        self.assertItemsEqual(
            Record.list(from_date=datetime(2014, 1, 4, 18, 0, 2)),
            self.records[1:3]
        )
        self.assertItemsEqual(
            Record.list(from_date=datetime(2014, 1, 4, 18, 0, 3)),
            self.records[1:2]
        )
        self.assertItemsEqual(
            Record.list(from_date=datetime(3000, 1, 1, 0, 0, 0)),
            []
        )

    def test_get_records_until_date(self):
        self.assertItemsEqual(
            Record.list(until_date=datetime(2014, 2, 22, 14, 45, 1)),
            self.records[0:4],

        )
        self.assertItemsEqual(
            Record.list(until_date=datetime(2013, 3, 19, 11, 1, 54)),
            [self.records[0], self.records[3]],

        )
        self.assertItemsEqual(
            Record.list(until_date=datetime(2013, 3, 19, 11, 1, 53)),
            [],

        )

    def test_get_records_in_range(self):
        # normal range
        self.assertItemsEqual(
            Record.list(from_date=datetime(2013, 3, 19, 11, 1, 54),
             until_date=datetime(2014, 2, 22, 14, 44, 59)),
            [self.records[0], self.records[2], self.records[3]],

        )

        # same from_date and until_date
        self.assertItemsEqual(
            Record.list(from_date=datetime(2014, 1, 4, 18, 0, 2),
             until_date=datetime(2014, 1, 4, 18, 0, 2)),
            self.records[2:3],

        )

        # no records in range
        self.assertItemsEqual(
            Record.list(from_date=datetime(2013, 3, 19, 11, 1, 55),
             until_date=datetime(2014, 1, 4, 18, 0, 1)),
            [],

        )

        # empty range
        self.assertItemsEqual(
            Record.list(from_date=datetime(2014, 1, 4, 18, 0, 3),
             until_date=datetime(2014, 1, 4, 18, 0, 2)),
            [],

        )

    def test_get_records_by_identifier(self):
        self.assertItemsEqual(
            Record.list(identifier='item1'),
            self.records[0:2]
        )
        self.assertItemsEqual(
            Record.list(identifier='invalid'),
            []
        )

    def test_get_records_resumption(self):
        self.assertItemsEqual(
            Record.list(limit=0),
            []
        )
        self.assertRaises(ValueError,
            lambda l: Record.list(limit=l), -1)
        self.assertItemsEqual(
            Record.list(limit=2),
            self.records[0:2]
        )
        self.assertItemsEqual(
            Record.list(offset='item2', limit=10),
            self.records[2:4]
        )
        self.assertItemsEqual(
            Record.list(offset='item1'),
            self.records
        )
        self.assertItemsEqual(
            Record.list(offset='item9'),
            []
        )

    def test_ignore_deleted(self):
        self.assertItemsEqual(
            Record.list(ignore_deleted=True),
            self.records[0:3]
        )


class TestUpdateRecords(ModelTestCase):

    def test_successful_update(self):
        time = datetime(1970, 1, 1, 0, 0, 0)
        for i in ['r', 's', 't', 'u']:
            Item.create(i)

        f = Format.create('a', 'http://a', 'a.xsd')
        data = make_xml(f)
        modified_data = data.replace('Test Record', 'droceR tseT')

        Record.create('r', 'a', data, time)
        Record.create('s', 'a', data, time)
        Record.create('t', 'a', data, time)

        updated = [
            ('u', 'a', modified_data), # new record, identifier exists
            ('r', 'a', modified_data), # old record, new data
            ('s', 'a', data),          # old record, old data
        ]
        for id_, prefix, data in updated:
            Record.create_or_update(id_, prefix, data)

        records = (DBSession.query(Record.identifier,
                                   Record.prefix,
                                   Record.xml)
                            .all())
        self.assertItemsEqual(records, [
            ('r', 'a', modified_data),
            ('s', 'a', data),
            ('t', 'a', data),
            ('u', 'a', modified_data),
        ])

        # Datestamps of records whose data does not change should not be
        # changed.
        unchanged = (DBSession.query(Record)
                              .filter_by(identifier='s')
                              .first())
        self.assertTrue(unchanged.datestamp == time)

        # Datestamp of updated record should be changed.
        changed = (DBSession.query(Record)
                            .filter_by(identifier='r')
                            .first())
        self.assertTrue(changed.datestamp > time)

    def test_ill_formed_xml(self):
        Item.create('oai:asd:id')
        f = make_format('oai_dc')
        r = Record.create('oai:asd:id', 'oai_dc', make_xml(f))
        with self.assertRaises(XMLSyntaxError):
            r.update('<test:dc><invalid xml/')


class TestDeleteRecords(ModelTestCase):

    def setUp(self):
        super(TestDeleteRecords, self).setUp()
        Item.create('item1')
        Item.create('item2')
        ddi = make_format('ddi')
        ead = make_format('ead')
        self.record1 = Record.create('item1', 'ddi', make_xml(ddi))
        self.record2 = Record.create('item1', 'ead', make_xml(ead))
        self.record3 = Record.create('item2', 'ddi', make_xml(ddi))

    def test_delete_single_record(self):
        Record.mark_as_deleted('item1', 'ddi')
        self.assertIs(self.record1.deleted, True)
        self.assertIs(self.record2.deleted, False)
        self.assertIs(self.record3.deleted, False)

    def test_delete_format(self):
        Record.mark_as_deleted(prefix='ddi')
        self.assertIs(self.record1.deleted, True)
        self.assertIs(self.record2.deleted, False)
        self.assertIs(self.record3.deleted, True)

    def test_delete_item(self):
        Record.mark_as_deleted(identifier='item1')
        self.assertIs(self.record1.deleted, True)
        self.assertIs(self.record2.deleted, True)
        self.assertIs(self.record3.deleted, False)


class TestDatestamp(ModelTestCase):

    def test_no_datestamp(self):
        """Should return `None` when datestamp is not set."""
        self.assertIs(Datestamp.get(), None)

    def test_many_datestamps(self):
        """Datestamp.update() should fix multiple datestamps."""
        Datestamp.create(datetime(2015, 1, 1, 12, 0, 0))
        Datestamp.create(datetime(2015, 1, 1, 22, 0, 0))
        Datestamp.update()
        self.assertEqual(len(DBSession.query(Datestamp).all()), 1)

    def test_datestamp_changes(self):
        """Datestamp should change whenever tokens could be invalidated."""
        second = timedelta(seconds=1)

        item1 = Item.create('i1')
        item2 = Item.create('i2')
        format_a = Format.create('a', 'urn:a', 'a.xsd')
        format_b = Format.create('b', 'urn:b', 'b.xsd')
        Record.create('i1', 'b', make_xml(format_b))

        date_mock = mock.Mock()

        # Datestamp changes when a new record is added.
        date_mock.return_value = datetime(1988,5,14, 9,29,2)
        with mock.patch.object(models, 'datestamp_now', date_mock):
            Record.create_or_update('i1', 'a', make_xml(format_a))
        self.assertEqual(Datestamp.get(), date_mock.return_value)

        # Datestamp changes when a record is modified.
        date_mock.return_value += second
        with mock.patch.object(models, 'datestamp_now', date_mock):
            new_data = make_xml(format_a).replace('testing', 'working')
            Record.create_or_update('i1', 'a', new_data)
        self.assertEqual(Datestamp.get(), date_mock.return_value)

        # Datestamp does not change when there is nothing to purge.
        old_date = date_mock.return_value
        date_mock.return_value += second
        with mock.patch.object(models, 'datestamp_now', date_mock):
            models.purge_deleted()
        self.assertEqual(Datestamp.get(), old_date)

        # Datestamp changes when a format with records is deleted.
        date_mock.return_value += second
        with mock.patch.object(models, 'datestamp_now', date_mock):
            format_b.mark_as_deleted()
        self.assertEqual(Datestamp.get(), date_mock.return_value)

        # Datestamp does not change when an item without records is
        # deleted.
        old_date = date_mock.return_value
        date_mock.return_value += second
        with mock.patch.object(models, 'datestamp_now', date_mock):
            item2.mark_as_deleted()
        self.assertEqual(Datestamp.get(), old_date)

        # Datestamp changes when an item with records is deleted.
        date_mock.return_value += second
        with mock.patch.object(models, 'datestamp_now', date_mock):
            item1.mark_as_deleted()
        self.assertEqual(Datestamp.get(), date_mock.return_value)

        # Datestamp changes when an records are purged.
        date_mock.return_value += second
        with mock.patch.object(models, 'datestamp_now', date_mock):
            models.purge_deleted()
        self.assertEqual(Datestamp.get(), date_mock.return_value)


class TestEarliestDatestamp(ModelTestCase):

    def test_has_earliest(self):
        dates = [
            datetime(2014, 3, 21, 13, 37, 59),
            datetime(2014, 3, 21, 13, 37, 59),
            datetime(2014, 3, 21, 13, 38, 00),
        ]
        f = Format.create('test', 'ns', 'schema.xsd')
        for i in xrange(0, 3):
            id_ = 'item{0}'.format(i)
            Item.create(id_)
            Record.create(id_, 'test', make_xml(f), dates[i])

        self.assertEqual(Record.earliest_datestamp(), dates[0])

    def test_no_records(self):
        Item.create('item1')
        Format.create('test', 'ns', 'schema.xsd')
        self.assertIs(Record.earliest_datestamp(), None)

    def test_ignore_deleted(self):
        dates = [
            datetime(2014, 4, 30, 13, 28, 14),
            datetime(2014, 4, 30, 13, 28, 15),
            datetime(2014, 4, 30, 13, 28, 16),
        ]
        items = [Item.create('item{0}'.format(i)) for i in xrange(1, 4)]
        f = Format.create('test', 'ns', 'schema.xsd')
        records = [Record.create(items[i].identifier,
                                 'test', make_xml(f), dates[i])
                   for i in xrange(0, 3)]
        records[0].deleted = True

        self.assertEqual(
            Record.earliest_datestamp(ignore_deleted=False),
            dates[0]
        )
        self.assertEqual(
            Record.earliest_datestamp(ignore_deleted=True),
            dates[1]
        )


class TestPurgeDeleted(ModelTestCase):

    def test_purge(self):
        Item.create('id1').deleted = True
        Item.create('id2')
        Item.create('id3')

        format_x = Format.create('x', 'urn:testx', 'x.xsd')
        format_x.deleted = True
        format_z = Format.create('z', 'urn:testz', 'z.zsd')

        Record.create('id1', 'x', make_xml(format_x)).deleted = True
        Record.create('id1', 'z', make_xml(format_z)).deleted = True
        Record.create('id2', 'x', make_xml(format_x)).deleted = True
        Record.create('id2', 'z', make_xml(format_z)).deleted = True
        existing = Record.create('id3', 'z', make_xml(format_z))

        models.purge_deleted()

        items = [i for (i,) in DBSession.query(Item.identifier).all()]
        self.assertItemsEqual(items, ['id2', 'id3'])

        self.assertEqual(DBSession.query(Format).all(), [format_z])
        self.assertEqual(DBSession.query(Record).all(), [existing])


class TestItemSetAssociations(ModelTestCase):

    def test_add_and_clear(self):
        i = Item.create('asdasd')
        s1 = Set.create('spec', 'Set Name')
        s2 = Set.create('spec2', 'Set Name II')
        i.add_to_set(s1)
        # Trying to add twice to the same set should not do anything.
        i.add_to_set(s1)
        self.assertEqual(
            (DBSession.query(Item).join(Item.sets)
                                  .filter(Set.spec=='spec')
                                  .all()),
            [i]
        )
        self.assertEqual(
            (DBSession.query(Item).join(Item.sets)
                                  .filter(Set.spec=='spec2')
                                  .all()),
            []
        )

        i.clear_sets()
        self.assertEqual(
            (DBSession.query(Item).join(Item.sets)
                                  .filter(Set.spec=='spec')
                                  .all()),
            []
        )

class TestSets(ModelTestCase):

    def test_create_set(self):
        Set.create('abcd', 'Set Name')
        Set.create('()()a-__!', 'Other Set')
        Set.create('()()a-__!:arst~\'**', 'Set Name')
        self.assertItemsEqual(
            DBSession.query(Set.spec, Set.name).all(),
            [('abcd', 'Set Name'),
             ('()()a-__!', 'Other Set'),
             ('()()a-__!:arst~\'**', 'Set Name')]
        )

    def test_invalid_spec(self):
        for spec in [u'äo-äo', 'abcd:', ':asd']:
            self.assertRaises(ValueError, Set.create, spec, 'Set Name')

    def test_create_or_update(self):
        s1 = Set.create('abcd', 'Asd')
        s2 = Set.create_or_update('efgh', 'Qwerty')
        s3 = Set.create_or_update('abcd', 'Ghjkl')
        self.assertIs(s1, s3)
        self.assertItemsEqual(
            DBSession.query(Set.spec, Set.name).all(),
            [('abcd', 'Ghjkl'), ('efgh', 'Qwerty')]
        )

    def test_list_sets(self):
        Set.create('a', 'Set A')
        Set.create('b', 'Set B')
        Set.create('b:c', 'Set C')
        self.assertItemsEqual(
            [(s.spec, s.name) for s in Set.list()],
            [('a', 'Set A'), ('b', 'Set B'), ('b:c', 'Set C')]
        )
