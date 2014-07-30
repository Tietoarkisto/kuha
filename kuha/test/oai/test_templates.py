import unittest
import re
from datetime import datetime

from lxml import etree
from pyramid import testing
from pyramid.renderers import render, get_renderer

from ..schema import master_schema

from ...util import (
    format_datestamp,
    filter_illegal_chars,
)
from ...exception import (
    BadArgument,
    ExpiredResumptionToken,
    IdDoesNotExist,
    InvalidResumptionToken,
    InvalidVerb,
    MissingVerb,
    NoMetadataFormats,
    NoRecordsMatch,
    NoSetHierarchy,
    RepeatedVerb,
    UnavailableMetadataFormat,
    UnsupportedMetadataFormat,
)


"""The namespaces."""
XSI_NS    = 'http://www.w3.org/2001/XMLSchema-instance'
OAI_NS    = 'http://www.openarchives.org/OAI/2.0/'
OAI_DC_NS = 'http://www.openarchives.org/OAI/2.0/oai_dc/'
DC_NS     = 'http://purl.org/dc/elements/1.1/'


"""The schema location for OAI DC metadata."""
OAI_DC_SCHEMA = u'http://www.openarchives.org/OAI/2.0/oai_dc.xsd'


class Format(object):
    """Dummy metadata format."""
    def __init__(self, prefix=u'oai_dc'):
        self.prefix = prefix
        if prefix == u'oai_dc':
            self.namespace = OAI_DC_NS
            self.schema = OAI_DC_SCHEMA
        else:
            self.namespace = 'urn:somenamespace'
            self.schema = 'http://example.org/someschema.xsd'


class Record(object):
    """Dummy record."""
    def __init__(self,
                 title='Test Record',
                 identifier='oai:example.org:item',
                 set_specs=[],
                 deleted=False):
        self.identifier = identifier
        self.prefix = u'oai_dc'
        self.set_specs = set_specs
        self.datestamp = datetime(2014, 4, 2, 12, 34, 56)
        self.deleted = deleted
        self.title = title
        if deleted:
            self.xml = None
        else:
            self.xml = '''
            <dc xmlns="{0}"
                xmlns:dc="{1}"
                xmlns:xsi="{2}"
                xsi:schemaLocation="{0} {3}">
                <dc:title>{4}</dc:title>
            </dc>
            '''.format(OAI_DC_NS, DC_NS, XSI_NS, OAI_DC_SCHEMA, title)


class Set(object):
    """Dummy set."""
    def __init__(self, spec):
        self.spec = spec
        self.name = 'Set Name'


def get_template_path(filename):
    return '../../oai/templates/{0}'.format(filename)


def parse_response(text):
    """Parse XML data and validate it using the OAI-PMH and oai_dc
    schemas. Return the parsed XML tree."""
    parser = etree.XMLParser(schema=master_schema())
    return etree.fromstring(text.encode('utf-8'), parser)


class TestErrorTemplate(unittest.TestCase):
    """Test the rendering of OAI-PMH errors."""

    def setUp(self):
        self.config = testing.setUp()
        self.config.include('pyramid_chameleon')

    def check_error_code(self, error, code):
        """Render the error template and check rendered error code."""
        template = get_template_path('error.pt')

        params = {
            'time': datetime(2013, 12, 24, 13, 45, 0),
            'format_date': format_datestamp,
            'filter_illegal_chars': filter_illegal_chars,
            'error': error,
        }

        request = testing.DummyRequest(params={
            'verb': 'ListSets',
            'resumptionToken': 'asdf'
        })
        setattr(request, 'path_url', 'http://pelle.org/asd')

        # render the template
        result = render(template, params, request)

        # parse and validate xml
        tree = parse_response(result)

        # check response date, base url, error code and message
        self.assertEqual(tree.find('{{{0}}}responseDate'.format(OAI_NS)).text,
                         '2013-12-24T13:45:00Z')
        self.assertEqual(tree.find('{{{0}}}request'.format(OAI_NS)).text,
                         'http://pelle.org/asd')
        self.assertEqual(tree.find('{{{0}}}error'.format(OAI_NS)).get('code'),
                         code)

        return tree

    def test_render_error(self):
        """Error code and message should be rendered correctly."""
        class Error(object):
            def code(self):
                return 'badResumptionToken'
            def message(self):
                return 'Some error message. </error>'

        tree = self.check_error_code(Error(), 'badResumptionToken')
        self.assertEqual(
            tree.find('{{{0}}}error'.format(OAI_NS)).text,
            'Some error message. </error>'
        )

    def test_invalid_xml_chars(self):
        identifier = u'\u0000 \u000b \ud888 \uffff'
        tree = self.check_error_code(IdDoesNotExist(identifier), 'idDoesNotExist')

    def test_error_objects(self):
        """All OAI exceptions should be properly rendered."""
        errors = [
            (BadArgument(''), 'badArgument'),
            (ExpiredResumptionToken(), 'badResumptionToken'),
            (IdDoesNotExist(''), 'idDoesNotExist'),
            (InvalidResumptionToken(), 'badResumptionToken'),
            (InvalidVerb(), 'badVerb'),
            (MissingVerb(), 'badVerb'),
            (NoMetadataFormats(''), 'noMetadataFormats'),
            (NoRecordsMatch(), 'noRecordsMatch'),
            (NoSetHierarchy(), 'noSetHierarchy'),
            (RepeatedVerb(), 'badVerb'),
            (UnavailableMetadataFormat('', ''), 'cannotDisseminateFormat'),
            (UnsupportedMetadataFormat(''), 'cannotDisseminateFormat'),
        ]
        for error, expected_code in errors:
            self.check_error_code(error, expected_code)


class OaiTemplateTest(unittest.TestCase):
    """Base class for template testcases."""

    def setUp(self):
        self.config = testing.setUp()
        self.config.include('pyramid_chameleon')

        self.request = testing.DummyRequest(params={'verb': self.verb})
        setattr(self.request, 'path_url', 'http://pelle.org/asd')
        self.values = {
            'time': datetime(2013, 12, 24, 13, 45, 0),
            'format_date': format_datestamp,
            'filter_illegal_chars': filter_illegal_chars,
        }

    def render_template(self, values):
        """Render the template with some parameters.
        """
        self.values.update(values)
        return render(self.template, self.values, self.request)

    def check_response(self, response, pattern):
        """Parse the response into an XML tree, validate it with the
        OAI-PMH schema and check that response matches the pattern.
        """
        # parse and validate xml
        tree = parse_response(response)

        # check root tag
        self.assertEqual(tree.tag, '{{{0}}}OAI-PMH'.format(OAI_NS))

        # check schema location
        self.assertEqual(
            tree.get('{{{0}}}schemaLocation'.format(XSI_NS)).split(),
            [OAI_NS, 'http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd']
        )

        # check response date and request elements
        self.assertEqual(tree.find('{%s}responseDate' % OAI_NS).text,
                         '2013-12-24T13:45:00Z')
        self.assertEqual(tree.find('{%s}request' % OAI_NS).text,
                         'http://pelle.org/asd')
        self.assertEqual(tree.find('{%s}request' % OAI_NS).attrib,
                         self.request.params)

        self.check_pattern(tree, pattern)

    def check_pattern(self, tree, pattern):
        if isinstance(pattern, basestring):
            self.assertEqual(tree.text, pattern)
        elif isinstance(pattern, tuple):
            self.check_element(tree, *pattern)
        elif isinstance(pattern, list):
            for p in pattern:
                self.check_pattern(tree, p)
        elif isinstance(pattern, dict):
            for p in pattern.iteritems():
                self.check_pattern(tree, p)

    def check_element(self, parent, tag, pattern):
        if tag.startswith('@'):
            self.check_attribute(parent, tag[1:], pattern)
        else:
            exceptions = []
            for elem in parent:
                if elem.tag.split('}')[-1] == tag:
                    try:
                        self.check_pattern(elem, pattern)
                        return elem
                    except Exception as e:
                        exceptions.append(e)
            else:
                exception_msg = '\n'.join(map(
                    lambda x: str(x).replace('\n', '\n    '),
                    exceptions,
                ))
                self.fail('XML does not match {0}:\n{1}'
                          ''.format(pattern, exception_msg))

    def check_attribute(self, element, name, expected):
        for qualname, value in element.attrib.iteritems():
            if qualname.split('}')[-1] == name:
                self.assertEqual(value, expected)
                return
        else:
            self.fail('Attribute "{0}" not found.'.format(name))

class TestIdentifyTemplate(OaiTemplateTest):
    """Test identify.pt template."""

    def setUp(self):
        self.verb = 'Identify'
        self.template = get_template_path('identify.pt')
        super(TestIdentifyTemplate, self).setUp()

    def test_single_admin(self):
        result = self.render_template({
            'repository_name': 'Unit Test Repository',
            'deleted_records': 'persistent',
            'admin_emails': ['admin@test.com'],
            'earliest': datetime(1970, 1, 1, 12, 0, 0),
            'repository_descriptions': [
                '''
<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/oai_dc/
                        http://www.openarchives.org/OAI/2.0/oai_dc.xsd">
    <dc:title>OAI-PMH Test Repository</dc:title>
    <dc:subject>oai-pmh</dc:subject>
    <dc:subject>software testing</dc:subject>
</oai_dc:dc>
                ''',
            ],
        })
        self.check_response(result, {'Identify': {
            'repositoryName': 'Unit Test Repository',
            'baseURL': self.request.path_url,
            'protocolVersion': '2.0',
            'adminEmail': 'admin@test.com',
            'deletedRecord': 'persistent',
            'earliestDatestamp': '1970-01-01T12:00:00Z',
            'description': {'dc': None},
        }})

    def test_many_admins(self):
        emails = ['admin@example.org',
                  'leet@example.org',
                  'hacker@example.org']
        result = self.render_template({
            'repository_name': 'Unit Test Repository',
            'admin_emails': emails,
            'deleted_records': 'no',
            'earliest': datetime(1970, 1, 1, 12, 0, 0),
            'repository_descriptions': [],
        })
        self.check_response(result,
            {'Identify': [('adminEmail', email) for email in emails]}
        )


class TestListFormats(OaiTemplateTest):
    """Test listformats.pt template."""

    def setUp(self):
        self.verb = 'ListMetadataFormats'
        self.template = get_template_path('listformats.pt')
        super(TestListFormats, self).setUp()

    def test_formats_for_id(self):
        self.request.params['identifier'] = 'oai:test.com:record'
        formats = [Format(u'oai_dc'), Format(u'test')]
        result = self.render_template({'formats': formats})
        self.check_response(result, {'ListMetadataFormats': [
            ('metadataFormat', {
                'metadataPrefix':    f.prefix,
                'schema':            f.schema,
                'metadataNamespace': f.namespace,
            }) for f in formats
        ]})


class TestGetRecord(OaiTemplateTest):
    """Test getrecord.pt template."""

    def setUp(self):
        self.verb = 'GetRecord'
        self.template = get_template_path('getrecord.pt')
        super(TestGetRecord, self).setUp()

    def test_get_record(self):
        r = Record(set_specs=['abc', 'def'])
        self.request.params['identifier'] = r.identifier
        self.request.params['metadataPrefix'] = r.prefix
        result = self.render_template({'record': r})
        self.check_response(result, {'GetRecord': {'record': {
            'header': [
                ('identifier', r.identifier),
                ('datestamp', format_datestamp(r.datestamp)),
                ('setSpec', 'abc'),
                ('setSpec', 'def'),
            ],
            'metadata': {'dc': {'title': r.title}},
        }}})

    def test_deleted_record(self):
        r = Record(deleted=True)
        self.request.params['identifier'] = r.identifier
        self.request.params['metadataPrefix'] = r.prefix

        result = self.render_template({'record': r})
        self.check_response(result, {'GetRecord': {'record': {'header': {
            'identifier': r.identifier,
            'datestamp': format_datestamp(r.datestamp),
            '@status': 'deleted',
        }}}})


class TestListRecords(OaiTemplateTest):
    """Test listrecords.pt template."""

    def setUp(self):
        self.verb = 'ListRecords'
        self.template = get_template_path('listrecords.pt')
        super(TestListRecords, self).setUp()

    def test_list_records(self):
        self.request.params.update({
            'metadataPrefix': 'oai_dc',
            'from': '2012-01-01',
            'until': '2016-01-01',
        })
        records = [Record('Rec 0', 'item0'),
                   Record('Rec 1', 'item1'),
                   Record('Rec 2', 'item2', deleted=True)]
        result = self.render_template({'records': records, 'token': None})
        self.check_response(result, {'ListRecords':
            [('record', {
                'header': {
                    'identifier': r.identifier,
                    'datestamp': format_datestamp(r.datestamp),
                },
                'metadata': {'dc': {'title': r.title}},
            }) for r in records[0:2]] +
            [('record', {'header': {
                'identifier': 'item2',
                'datestamp': format_datestamp(records[2].datestamp),
                '@status': 'deleted',
            }})]
        })

    def test_request_token(self):
        self.request.params.update({'metadataPrefix': 'oai_dc'})
        result = self.render_template({
            'records': [Record()],
            'token': 'oairnt/3k2<><)>)<>))<>//>>>>',
        })
        self.check_response(result, {'ListRecords':
            {'resumptionToken': 'oairnt/3k2<><)>)<>))<>//>>>>'},
        })


class TestListIdentifiers(OaiTemplateTest):
    """Test listidentifiers.pt template."""

    def setUp(self):
        self.verb = 'ListIdentifiers'
        self.template = get_template_path('listidentifiers.pt')
        super(TestListIdentifiers, self).setUp()

    def test_list_identifiers(self):
        self.request.params.update({
            'metadataPrefix': 'oai_dc',
            'from': '1970-01-01',
        })
        records = [Record('Rec 0', 'item0'),
                   Record('Rec 1', 'item1'),
                   Record('Rec 2', 'item2', deleted=True)]
        result = self.render_template({
            'records': records,
            'token': '{1234}',
        })
        self.check_response(result, {'ListIdentifiers':
            [('header', {
                'identifier': r.identifier,
                'datestamp': format_datestamp(r.datestamp),
            }) for r in records[0:2]] +
            [('header', {
                'identifier': 'item2',
                'datestamp': format_datestamp(records[2].datestamp),
                '@status': 'deleted',
            })] +
            [('resumptionToken', '{1234}')]
        })

    def test_no_request_token(self):
        self.request.params.update({
            'metadataPrefix': 'oai_dc',
        })
        result = self.render_template({
            'records': [Record()],
            'token': None,
        })
        self.check_response(result, [])


class TestListSets(OaiTemplateTest):
    """Test listsets.pt template."""

    def setUp(self):
        self.verb = 'ListSets'
        self.template = get_template_path('listsets.pt')
        super(TestListSets, self).setUp()

    def test_list_sets(self):
        sets = [Set('abc'), Set('def')]
        result = self.render_template({'sets': sets})
        self.check_response(result, {'ListSets': [
            ('set', {'setSpec': s.spec, 'setName': s.name})
            for s in sets
        ]})
