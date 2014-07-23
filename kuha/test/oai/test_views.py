import unittest
from datetime import datetime
import json

import mock
from pyramid import testing
from webob.multidict import MultiDict

from ...oai import views
from ...util import datestamp_now
from ...exception import (
    OaiException,

    BadArgument,
    MissingVerb,
    InvalidVerb,
    RepeatedVerb,

    IdDoesNotExist,
    NoSetHierarchy,
    NoRecordsMatch,
    NoMetadataFormats,
    UnsupportedMetadataFormat,
    UnavailableMetadataFormat,

    InvalidResumptionToken,
    ExpiredResumptionToken,
)


class Data(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class ViewTestCase(unittest.TestCase):
    verb = None
    function = None

    def setUp(self):
        self.config = testing.setUp()
        self.config.include('pyramid_chameleon')

    def tearDown(self):
        testing.tearDown()

    def minimal_params(self):
        """Return a multidict containing minimal request parameters that
        are needed to successfully call the view function.
        """
        return MultiDict(verb=self.verb)

    def check_response(self,
                       response,
                       **kwargs):
        """Check that a response contains the expected values."""
        self.assertTrue('time' in response)

        for key, value in kwargs.iteritems():
            self.assertEqual(response[key], value)

    def check_token(self, response, token):
        """Check that a resumption token contains the expected values."""
        attributes = ['verb',
                      'metadataPrefix',
                      'offset',
                      'from',
                      'until']
        parsed = json.loads(response['token'])
        self.assertIn('date', parsed)
        for a in attributes:
            self.assertEqual(parsed[a], token[a])


class TestErrorView(ViewTestCase):
    def test_error_view(self):
        error = OaiException()
        self.check_response(
            views.oai_error_view(error, testing.DummyRequest()),
            error=error,
        )


class TestInvalidVerb(ViewTestCase):
    def test_missing_verb(self):
        request = testing.DummyRequest()
        self.assertRaises(MissingVerb, views.invalid_verb_view, request)

    def test_invalid_verb(self):
        request = testing.DummyRequest(
            params=MultiDict(verb='NoGoodVerb'))
        self.assertRaises(InvalidVerb, views.invalid_verb_view, request)


class InvalidArgumentMixin(object):
    def test_invalid_argument(self):
        params = self.minimal_params()
        params['invalidArgument'] = 'value'
        request = testing.DummyRequest(params=params)
        self.assertRaises(BadArgument, self.function, request)


class RepeatedVerbMixin(object):
    def test_repeated_verb(self):
        params = MultiDict()
        params.add('verb', self.verb)
        params.add('verb', self.verb)
        request = testing.DummyRequest(params=params)
        self.assertRaises(RepeatedVerb, self.function, request)


class TestIdentifyView(ViewTestCase,
                       InvalidArgumentMixin,
                       RepeatedVerbMixin):

    def setUp(self):
        self.verb = 'Identify'
        self.function = views.handle_identify
        super(TestIdentifyView, self).setUp()

        self.config.get_settings()['repository_name'] = 'repo'
        self.config.get_settings()['admin_emails'] = [
            'leet@example.org',
            'hacker@example.org',
        ]
        self.config.get_settings()['deleted_records'] = 'transient'
        self.config.get_settings()['repository_descriptions'] = [
            '<description1/>',
            '<description2/>',
        ]

    @mock.patch.object(views, 'Record')
    def test_identify(self, mock_obj):
        """Identify should return the configured information."""
        date = datetime(2014, 3, 21, 15, 47, 37)
        mock_obj.earliest_datestamp.return_value = date

        request = testing.DummyRequest(params=self.minimal_params())
        self.check_response(
            self.function(request),
            earliest=date,
            repository_name='repo',
            deleted_records='transient',
            admin_emails=['leet@example.org', 'hacker@example.org'],
            repository_descriptions=['<description1/>', '<description2/>'],
        )
        mock_obj.earliest_datestamp.assert_called_once_with(False)

    @mock.patch.object(views, 'Record')
    def test_identify_none_datestamp(self, mock_func):
        """Earliest datestamp should be the current time when there are no
        records.
        """
        mock_func.earliest_datestamp.return_value = None
        now = datestamp_now()
        result = self.function(
            testing.DummyRequest(params=self.minimal_params()))
        self.assertTrue(result['earliest'] >= now)


class TestListSetsView(ViewTestCase,
                       RepeatedVerbMixin):
    def setUp(self):
        self.verb = 'ListSets'
        self.function = views.handle_list_sets
        super(TestListSetsView, self).setUp()

    @mock.patch.object(views, 'Set')
    def test_no_set_hierarchy(self, set_mock):
        """View should raise NoSetHierarchy."""
        set_mock.list.return_value = []
        request = testing.DummyRequest(params=self.minimal_params())
        self.assertRaises(NoSetHierarchy, self.function, request)

    @mock.patch.object(views, 'Set')
    def test_has_sets(self, set_mock):
        """View should raise NoSetHierarchy."""
        sets = [mock.Mock(), mock.Mock()]
        set_mock.list.return_value = sets
        request = testing.DummyRequest(params=self.minimal_params())
        result = self.function(request)
        self.assertItemsEqual(result['sets'], sets)

    @mock.patch.object(views, 'Datestamp')
    def test_invalid_resumption(self, date_mock):
        """Using a resumption token should raise InvalidResumptionToken."""
        date_mock.get.return_value = datetime(2000, 4, 5, 12, 3, 4)
        token = {'verb': self.verb, 'date': '2015-04-01', 'offset': 'a'}
        request = testing.DummyRequest(params=MultiDict(
            verb=self.verb,
            resumptionToken=json.dumps(token),
        ))
        self.assertRaises(InvalidResumptionToken, self.function, request)

    @mock.patch.object(views, 'Datestamp')
    def test_expired_resumption(self, date_mock):
        """Using an expired token should raise InvalidResumptionToken."""
        date_mock.get.return_value = datetime(3100, 4, 5, 12, 3, 4)
        token = {'verb': self.verb, 'date': '2015-04-01', 'offset': 'a'}
        request = testing.DummyRequest(params=MultiDict(
            verb=self.verb,
            resumptionToken=json.dumps(token),
        ))
        self.assertRaises(InvalidResumptionToken, self.function, request)


class TestListFormatsView(ViewTestCase,
                          InvalidArgumentMixin,
                          RepeatedVerbMixin):
    def setUp(self):
        self.verb = 'ListMetadataFormats'
        self.function = views.handle_list_metadata_formats
        super(TestListFormatsView, self).setUp()
        self.config.add_settings(deleted_records='transient')

    @mock.patch.object(views, 'Format')
    def test_list_all_formats(self, format_mock):
        formats = [Data(prefix='oai_dc'), Data(prefix='ead')]
        format_mock.list.return_value = formats

        request = testing.DummyRequest(params=self.minimal_params())

        self.check_response(self.function(request), formats=formats)
        format_mock.list.assert_called_once_with(None, False)

    @mock.patch.object(views, 'Format')
    @mock.patch.object(views, 'Item')
    def test_list_for_one_item(self, item_mock, format_mock):
        formats = [Data(prefix='oai_dc')]
        format_mock.list.return_value = formats
        item_mock.exists.return_value = True

        params = self.minimal_params()
        params['identifier'] = 'item'
        request = testing.DummyRequest(params=params)

        self.check_response(self.function(request), formats=formats)
        item_mock.exists.assert_called_once_with('item', False)
        format_mock.list.assert_called_once_with('item', False)

    @mock.patch.object(views, 'Item')
    def test_invalid_identifier(self, item_mock):
        item_mock.exists.return_value = False
        params = self.minimal_params()
        params['identifier'] = 'unexistingId'
        request = testing.DummyRequest(params=params)

        self.assertRaises(IdDoesNotExist, self.function, request)
        item_mock.exists.assert_called_once_with('unexistingId', False)

    @mock.patch.object(views, 'Format')
    @mock.patch.object(views, 'Item')
    def test_no_available_formats(self, item_mock, format_mock):
        item_mock.exists.return_value = True
        format_mock.list.return_value = []

        params = self.minimal_params()
        params['identifier'] = 'item'
        request = testing.DummyRequest(params=params)

        self.assertRaises(NoMetadataFormats, self.function, request)
        item_mock.exists.assert_called_once_with('item', False)
        format_mock.list.assert_called_once_with('item', False)


class TestListItemsView(ViewTestCase,
                        InvalidArgumentMixin,
                        RepeatedVerbMixin):

    def setUp(self):
        self.verb = 'ListRecords'
        self.function = views.handle_list_items
        # some test data
        self.records = [
            Data(identifier='a', prefix='dummy'),
            Data(identifier='b', prefix='dummy'),
            Data(identifier='c', prefix='dummy'),
        ]
        super(TestListItemsView, self).setUp()
        self.config.add_settings(item_list_limit=4)
        self.config.add_settings(deleted_records='transient')

    def minimal_params(self):
        return MultiDict(
            verb=self.verb,
            metadataPrefix='dummy', # metadata prefix is required
        )

    def test_list_all_records(self):
        params = self.minimal_params()

        with mock.patch.object(views, '_get_records') as mock_func:
            mock_func.return_value = (['1', '2'], '3')
            result = self.function(testing.DummyRequest(params=params))

        self.check_response(result, records=['1', '2'])
        self.check_token(result, {
            u'verb': u'ListRecords',
            u'metadataPrefix': u'dummy',
            u'offset': u'3',
            u'set': None,
            u'from': None,
            u'until': None,
        })
        mock_func.assert_called_once_with(params, False, 4)

    def test_list_identifiers(self):
        """View should handle ListIdentifiers as well."""
        self.verb = 'ListIdentifiers'
        params = self.minimal_params()
        params['verb'] = self.verb

        with mock.patch.object(views, '_get_records') as mock_func:
            mock_func.return_value = ([1, 2], None)
            result = self.function(testing.DummyRequest(params=params))

        self.check_response(result, records=[1, 2])
        mock_func.assert_called_once_with(params, False, 4)

    @mock.patch.object(views, 'Format')
    @mock.patch.object(views, 'Record')
    @mock.patch.object(views, 'Set')
    def test_resumption(self, set_mock, record_mock, format_mock):
        set_mock.list.return_value = [mock.Mock]
        record_mock.list.return_value = self.records
        format_mock.exists.return_value = True
        token_mock = mock.Mock(return_value={
            'verb': self.verb,
            'metadataPrefix': 'dummy',
            'offset': 'b',
            'date': '2014-03-31',
            'from': '1970-01-01',
            'until': '2140-01-01',
            'set': 'math:geometry',
        })

        request = testing.DummyRequest(params=MultiDict(
            verb=self.verb,
            resumptionToken='token',
        ))

        with mock.patch.object(views, '_get_resumption_token', token_mock):
            result = self.function(request)

        self.check_response(result, records=self.records, token='')
        record_mock.list.assert_called_once_with(
            metadata_prefix='dummy',
            from_date=datetime(1970, 1, 1, 0, 0, 0),
            until_date=datetime(2140, 1, 1, 23, 59, 59),
            set_='math:geometry',
            ignore_deleted=False,
            offset='b', limit=5,
        )
        token_mock.assert_called_once_with(request)

    @mock.patch.object(views, 'Format')
    def test_resumption_invalid_argument(self, format_mock):
        """Should raise InvalidResumptionToken when token contain invalid
        arguments."""
        request = testing.DummyRequest(params=MultiDict(
            verb=self.verb,
            resumptionToken='token',
        ))

        format_mock.exists.return_value = False
        token_mock = mock.Mock(return_value={
            'verb': self.verb,
            'metadataPrefix': 'dummy', # non-existent format
            'offset': 'b',
            'from': None,
            'until': None,
            'set': None,
            'date': '2014-04-08T15:37:56Z',
        })
        with mock.patch.object(views, '_get_resumption_token', token_mock):
            self.assertRaises(InvalidResumptionToken,
                              self.function,
                              request)

        class MatchRequest(object):
            def __eq__(self, req):
                return req.params == {
                    'verb': 'ListRecords',
                    'resumptionToken': 'token',
                }
        token_mock.assert_called_once_with(MatchRequest())
        format_mock.exists.assert_called_once_with('dummy', False)

    def test_resumption_expired(self):
        request = testing.DummyRequest(params=MultiDict(
            verb=self.verb,
            resumptionToken='token',
        ))

        token_mock = mock.Mock(side_effect=ExpiredResumptionToken())
        with mock.patch.object(views, '_get_resumption_token', token_mock):
            self.assertRaises(ExpiredResumptionToken,
                              self.function,
                              request)


class TestGetRecords(unittest.TestCase):

    def setUp(self):
        self.test_params = {
            u'verb': u'ListRecords',
            u'metadataPrefix': u'prefix',
            u'from': u'2014-01-30',
            u'until': u'2014-02-01',
            u'set': u'abcde',
        }

    @mock.patch.object(views, 'Format')
    def test_invalid_prefix(self, format_mock):
        format_mock.exists.return_value = False
        self.assertRaises(UnsupportedMetadataFormat,
                          views._get_records,
                          self.test_params, False, 10)
        format_mock.exists.assert_called_once_with(u'prefix', False)

    @mock.patch.object(views, 'Format')
    @mock.patch.object(views, 'Set')
    def test_no_set_hierarchy(self, set_mock, format_mock):
        set_mock.list.return_value = []
        format_mock.exists.return_value = True
        self.assertRaises(NoSetHierarchy,
                          views._get_records,
                          self.test_params, False, 10)

    @mock.patch.object(views, 'Format')
    @mock.patch.object(views, 'Record')
    @mock.patch.object(views, 'Set')
    def test_no_matching_records(self,
                                 set_mock,
                                 record_mock,
                                 format_mock):
        set_mock.list.return_value = [mock.Mock()]
        format_mock.exists.return_value = True
        record_mock.list.return_value = []
        self.assertRaises(NoRecordsMatch,
                          views._get_records,
                          self.test_params, True, 10)
        record_mock.list.assert_called_once_with(
            metadata_prefix='prefix',
            from_date=datetime(2014, 1, 30, 0, 0, 0),
            until_date=datetime(2014, 2, 1, 23, 59, 59),
            set_=u'abcde',
            ignore_deleted=True,
            offset=None, limit=11,
        )

    @mock.patch.object(views, 'Format')
    @mock.patch.object(views, 'Record')
    @mock.patch.object(views, 'Set')
    def test_limited_list(self, set_mock, record_mock, format_mock):
        set_mock.list.return_value = [mock.Mock()]
        model_records = [
            Data(identifier='1', prefix='prefix', xml='data'),
            Data(identifier='2', prefix='prefix', xml='data'),
            Data(identifier='3', prefix='prefix', xml='data'),
            Data(identifier='4', prefix='prefix', xml='data'),
        ]
        record_mock.list.return_value = model_records
        format_mock.exists.return_value = True

        records, offset = views._get_records(self.test_params, False, 3)

        self.assertEqual(records, model_records[0:3])
        self.assertEqual(offset, '4')
        record_mock.list.assert_called_once_with(
            metadata_prefix='prefix',
            from_date=datetime(2014, 1, 30, 0, 0, 0),
            until_date=datetime(2014, 2, 1, 23, 59, 59),
            set_=u'abcde',
            ignore_deleted=False,
            offset=None, limit=4,
        )


class TestGetResumptionToken(unittest.TestCase):

    def setUp(self):
        self.token_dict = {
            'verb': 'ListRecords',
            'metadataPrefix': 'dummy',
            'from': None, 'until': '2014-04-08T14:55:52Z',
            'set': 'set:spec',
            'offset': 'a',
            'date': '2014-01-01',
        }
        self.config = testing.setUp()
        self.config.include('pyramid_chameleon')

    def tearDown(self):
        testing.tearDown()

    @mock.patch.object(views, 'Datestamp')
    def test_valid_token(self, date_mock):
        date_mock.get.return_value = datetime(2000, 1, 1, 0, 0, 0)
        request = testing.DummyRequest(params=MultiDict(
            verb='ListRecords',
            resumptionToken=json.dumps(self.token_dict),
        ))
        token = views._get_resumption_token(request)
        self.assertEqual(token, self.token_dict)

    @mock.patch.object(views, 'Datestamp')
    def test_no_token(self, date_mock):
        date_mock.get.return_value = datetime(2000, 1, 1, 0, 0, 0)
        request = testing.DummyRequest(params=MultiDict(
            verb='ListIdentifiers',
            metadataPrefix='oai_dc',
        ))
        self.assertIsNone(views._get_resumption_token(request))

    @mock.patch.object(views, 'Datestamp')
    def test_token_expired(self, date_mock):
        date_mock.get.return_value = datetime(2000, 1, 1, 0, 0, 0)
        self.token_dict['date'] = '1970-01-01'
        request = testing.DummyRequest(params=MultiDict(
            verb='ListRecords',
            resumptionToken=json.dumps(self.token_dict),
        ))
        self.assertRaises(ExpiredResumptionToken,
                          views._get_resumption_token,
                          request)

    def _test_invalid_token(self, token):
        """
        Assert that _get_resumption_token raises InvalidResumptionToken
        with the given token.
        """
        request = testing.DummyRequest(params=MultiDict(
            verb='ListRecords',
            resumptionToken=token,
        ))
        self.assertRaises(InvalidResumptionToken,
                          views._get_resumption_token,
                          request)

    def test_invalid_json(self):
        self._test_invalid_token('Not a valid resumption token.')

    def test_invalid_type(self):
        self._test_invalid_token(json.dumps(
            ['ListRecords', 'dummy', '1970-01-01', None, None, 'a']
        ))

    def test_wrong_verb(self):
        self.token_dict['verb'] = 'ListSets'
        self._test_invalid_token(json.dumps(self.token_dict))

    def test_no_verb(self):
        del self.token_dict['verb']
        self._test_invalid_token(json.dumps(self.token_dict))

    def test_no_date(self):
        del self.token_dict['date']
        self._test_invalid_token(json.dumps(self.token_dict))

    def test_invalid_arg_type(self):
        self.token_dict['from'] = 5
        self._test_invalid_token(json.dumps(self.token_dict))

    def test_invalid_date_format(self):
        self.token_dict['date'] = '01.01.2014'
        self._test_invalid_token(json.dumps(self.token_dict))


class TestGetRecordView(ViewTestCase,
                        InvalidArgumentMixin,
                        RepeatedVerbMixin):
    def setUp(self):
        self.verb = 'GetRecord'
        self.function = views.handle_get_record
        super(TestGetRecordView, self).setUp()
        self.config.add_settings(deleted_records='no')
        # test data
        self.record = Data(identifier='item', prefix='dummy', xml='data')

    def minimal_params(self):
        return MultiDict(
            verb=self.verb,
            metadataPrefix='dummy',
            identifier='item',
        )

    @mock.patch.object(views, 'Record')
    @mock.patch.object(views, 'Format')
    @mock.patch.object(views, 'Item')
    def test_get_record(self, item_mock, format_mock, record_mock):
        """Calling with valid params should fetch the record."""
        item_mock.exists.return_value = True
        format_mock.exists.return_value = True
        record_mock.list.return_value = [self.record]
        request = testing.DummyRequest(params=self.minimal_params())

        result = self.function(request)

        self.check_response(result, record=self.record)
        item_mock.exists.assert_called_once_with('item', True)
        format_mock.exists.assert_called_once_with('dummy', True)
        record_mock.list.assert_called_once_with(
            identifier='item',
            metadata_prefix='dummy',
            ignore_deleted=True,
        )

    @mock.patch.object(views, 'Format')
    @mock.patch.object(views, 'Item')
    def test_invalid_prefix(self, item_mock, format_mock):
        item_mock.exists.return_value = True
        format_mock.exists.return_value = False
        request = testing.DummyRequest(params=self.minimal_params())

        self.assertRaises(UnsupportedMetadataFormat,
                          self.function,
                          request)
        format_mock.exists.assert_called_once_with('dummy', True)

    @mock.patch.object(views, 'Format')
    @mock.patch.object(views, 'Item')
    def test_invalid_identifier(self, item_mock, format_mock):
        item_mock.exists.return_value = False
        format_mock.exists.return_value = True
        request = testing.DummyRequest(params=self.minimal_params())

        self.assertRaises(IdDoesNotExist, self.function, request)
        item_mock.exists.assert_called_once_with('item', True)

    @mock.patch.object(views, 'Record')
    @mock.patch.object(views, 'Format')
    @mock.patch.object(views, 'Item')
    def test_unavailable_format(self, item_mock, format_mock, record_mock):
        item_mock.exists.return_value = True
        format_mock.exists.return_value = True
        record_mock.list.return_value = []
        request = testing.DummyRequest(params=self.minimal_params())

        self.assertRaises(UnavailableMetadataFormat,
                          self.function,
                          request)


class TestCheckParams(unittest.TestCase):
    def test_valid_params(self):
        views._check_params(
            params=MultiDict(
                verb='Verb',
                allowed1='value',
                required='value',
            ),
            required=['required'],
            allowed=['allowed1', 'allowed2'],
        )
        # Pass if no exception is raised.

    def test_missing_verb(self):
        self.assertRaises(MissingVerb, views._check_params, [])

    def test_repeated_argument(self):
        params = MultiDict(verb='a')
        params.add('repeated', 'b')
        params.add('repeated', 'b')
        self.assertRaises(BadArgument,
                          views._check_params,
                          params,
                          ['repeated'])

    def test_missing_required(self):
        self.assertRaises(BadArgument,
                          views._check_params,
                          MultiDict(verb='a'),
                          ['param'])

    def test_invalid_argument(self):
        self.assertRaises(BadArgument,
                          views._check_params,
                          MultiDict(verb='a', invalid='b'))


class TestParseFromAndUntil(unittest.TestCase):

    def test_invalid_from_format(self):
        self.assertRaises(BadArgument,
                          views._parse_from_and_until,
                          'asdasd', '2014-02-02')

    def test_invalid_until_format(self):
        self.assertRaises(BadArgument,
                          views._parse_from_and_until,
                          '2014-02-02', 'asdasd')

    def test_invalid_granularities(self):
        self.assertRaises(BadArgument,
                          views._parse_from_and_until,
                          '2014-02-02', '2014-02-02T22:00:00Z')

    def test_invalid_date_range(self):
        self.assertRaises(BadArgument,
                          views._parse_from_and_until,
                          '2014-03-01', '2014-02-01')

    def test_successful_parse(self):
        from_date, until_date = views._parse_from_and_until(
            '2014-03-03', '2014-04-04')
        self.assertEqual(from_date,
                         datetime(2014,03,03, 00,00,00))
        self.assertEqual(until_date,
                         datetime(2014,04,04, 23,59,59))
