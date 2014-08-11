# encoding: utf-8

import unittest

import mock

from ..exception import ConfigurationError
from .. import config

class TestCleanSettings(unittest.TestCase):

    def test_valid_settings(self):
        settings = {
            'a': [],
            'b': None,
            'c': '4',
        }
        cleaners = {
            'a': mock.Mock(),
            'c': mock.Mock()
        }
        config._clean_settings(settings, cleaners)

        self.assertIs(settings['a'], cleaners['a'].return_value)
        self.assertIsNone(settings['b'])
        self.assertIs(settings['c'], cleaners['c'].return_value)

    def test_missing_value(self):
        settings = {'x': 'y'}
        cleaners = {'a': mock.Mock()}

        self.assertRaises(ConfigurationError,
                          config._clean_settings,
                          settings, cleaners)
        self.assertEqual(cleaners['a'].mock_calls, [])

    def test_invalid_value(self):
        settings = {'setting': '   '}
        cleaners = {'setting': mock.Mock(side_effect=TypeError())}

        self.assertRaises(ConfigurationError,
                          config._clean_settings,
                          settings, cleaners)
        cleaners['setting'].assert_called_once_with('   ')


class TestCleanAdminEmails(unittest.TestCase):

    def test_valid_emails(self):
        emails = u'''
            leet@example.org
            admin@test.org
            asd@asd.asd
            ä"@"#*'"\\"\\"ää@ööÖÖ.Ä
        '''.encode('utf-8')
        result = config._clean_admin_emails(emails)
        self.assertEqual(
            result,
            [u'leet@example.org',
             u'admin@test.org',
             u'asd@asd.asd',
             u'ä"@"#*\'"\\"\\"ää@ööÖÖ.Ä',
            ]
        )
        for r in result:
            self.assertIs(type(r), unicode)

    def test_invalid_email(self):
        self.assertRaises(ValueError,
                          config._clean_admin_emails,
                          'invalid_email')

    def test_no_emails(self):
        self.assertRaises(ValueError,
                          config._clean_admin_emails,
                          '')


class TestCleanDeletedRecords(unittest.TestCase):

    def test_valid_values(self):
        for v in ['no', u'transient', 'persistent']:
            result = config._clean_deleted_records(v)
            self.assertIs(type(result), unicode)
            self.assertEqual(result, v)

    def test_invalid_value(self):
        self.assertRaises(ValueError,
                          config._clean_deleted_records,
                          u'asd')


class TestCleanBoolean(unittest.TestCase):

    def test_true(self):
        for value in ['y', 'Y', '1', 'yes', 'Yes', 'YES',
                      'true', 'True', 'TRUE', 'on', 'On', 'ON']:
            self.assertIs(config._clean_boolean(value), True)

    def test_false(self):
        for value in ['no', 'false', 'off', '']:
            self.assertIs(config._clean_boolean(value), False)


class TestCleanItemListLimit(unittest.TestCase):

    def test_valid_limit(self):
        self.assertEqual(config._clean_item_list_limit('42'), 42)

    def test_invalid_limit(self):
        for value in [-100, -1, 0, 'abc']:
            self.assertRaises(ValueError,
                              config._clean_item_list_limit,
                              value)


class TestCleanUnicode(unittest.TestCase):

    def test_valid_values(self):
        cases = [
            ('text', u'text'),
            (u'arsdÄÖOä', u'arsdÄÖOä'),
            (u'ÄÖä'.encode('utf-8'), u'ÄÖä'),
        ]
        for input_, expected in cases:
            actual = config._clean_unicode(input_)
            self.assertEqual(actual, expected)
            self.assertIs(type(actual), unicode)

    def test_invalid_encoding(self):
        with self.assertRaises(UnicodeError):
            config._clean_unicode('\xFA')


class TestCleanProviderClass(unittest.TestCase):

    def test_valid_name(self):
        self.assertEqual(
            config._clean_provider_class('some.module.name:ClassName'),
            ('some.module.name', 'ClassName'),
        )

    def test_invalid_values(self):
        values = [
            'some.module.name:ClassName:morestuff',
            'abcdefghi',
            'module:',
            ':ClassName',
            '',
        ]
        for value in values:
            with self.assertRaises(ValueError):
                config._clean_provider_class(value)


class TestLoadRepositoryDescriptions(unittest.TestCase):

    def test_valid_descriptions(self):
        data = '''
            <test
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                xsi:schemaLocation="urn:test http://example.org/test.xsd">
                <text attr="value">
                    Test Description
                </text>
            </test>
        '''
        setting = '\n    somefilename.xml\n'

        open_mock = mock.mock_open(read_data=data)
        with mock.patch.object(config, 'open', open_mock, create=True):
            result = config._load_repository_descriptions(setting)

        open_mock.assert_called_once_with('somefilename.xml', 'r')
        self.assertEqual(result, [data])

    def test_io_error(self):
        open_mock = mock.mock_open()
        open_mock.return_value.read.side_effect = IOError(
            'cannot read file'
        )
        with mock.patch.object(config, 'open', open_mock, create=True):
            with self.assertRaises(IOError) as cm:
                config._load_repository_descriptions('file.xml')
            self.assertIn('cannot read file', cm.exception.message)
        open_mock.assert_called_once_with('file.xml', 'r')

    def test_illformed_xml(self):
        open_mock = mock.mock_open(read_data='asdasd')
        with mock.patch.object(config, 'open', open_mock, create=True):
            with self.assertRaises(ValueError) as cm:
                config._load_repository_descriptions('file.xml')
            self.assertIn('ill-formed XML', cm.exception.message)
        open_mock.assert_called_once_with('file.xml', 'r')

    def test_missing_schema(self):
        data = '''
            <test>
                <text attr="value">
                    Test Description
                </text>
            </test>
        '''
        open_mock = mock.mock_open(read_data=data)
        with mock.patch.object(config, 'open', open_mock, create=True):
            with self.assertRaises(ValueError) as cm:
                config._load_repository_descriptions('file.xml')
            self.assertIn('no schema location', cm.exception.message)
        open_mock.assert_called_once_with('file.xml', 'r')
