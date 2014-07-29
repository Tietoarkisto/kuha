import os
import logging
from datetime import datetime

from lxml import etree

class DdiFileProvider(object):
    """
    Metadata provider for DDI Codebook XML files.

    This provider scans a directory for XML files and converts them from
    DDI Codebook to OAI DC.
    """

    def __init__(self, domain_name='example.org', directory='.'):
        """
        Initialize the metadata provider.

        Parameters
        ----------
        directory: str
            Path of the directory to scan for DDI files.
        domain_name: str
            The domain name part of the OAI identifiers.
        """
        self.oai_identifier_prefix = 'oai:{0}:'.format(domain_name)
        self.directory = directory

    def formats(self):
        """
        List the available metadata formats.

        Return
        ------
        dict from unicode to (unicode, unicode):
            Mapping from metadata prefixes to (namespace, schema location)
            tuples.
        """
        # Only OAI DC is available from this provider.
        return {
            'oai_dc': ('http://www.openarchives.org/OAI/2.0/oai_dc/',
                       'http://www.openarchives.org/OAI/2.0/oai_dc.xsd'),
        }

    def identifiers(self):
        """
        List all identifiers.

        Return
        ------
        iterable of str:
            OAI identifiers of all items
        """
        logging.debug('Scanning directory {0} for XML files...'
                      ''.format(self.directory))
        # List all xml files and turn the filenames into identifiers.
        file_count = 0
        for subdir, _, files in os.walk(self.directory):
            for filename in files:
                if filename.lower().endswith('.xml'):
                    path = os.path.join(subdir, filename)
                    yield self.make_identifier(path)
                    file_count += 1
        if file_count == 0:
            logging.warning('No XML files found in {0}'
                            ''.format(self.directory))

    def has_changed(self, identifier, since):
        """
        Check wheter the given item has been modified.

        Parameters
        ----------
        identifier: unicode
            The OAI identifier (as returned by identifiers()) of the item.
        since: datetime.datetime
            Ignore modifications before this date/time.

        Return
        ------
        bool:
            `True`, if metadata or sets of the item have change since the
            given time. Otherwise `False`.
        """
        filename = self.get_filename(identifier)
        path = os.path.join(self.directory, filename)
        mtime = os.path.getmtime(path)
        ctime = os.path.getctime(path)
        datestamp = datetime.utcfromtimestamp(max(mtime, ctime))
        return datestamp >= since

    def get_sets(self, identifier):
        """
        List sets of an item.

        Parameters
        ----------
        identifier: unicode
            The OAI identifier (as returned by identifiers()) of the item.

        Return
        ------
        iterable of (unicode, unicode):
            (set spec, set name) pairs for all sets which contain the given
            item. In case of hierarchical sets, return all sets in the
            hierarchy (e.g. if the result contains the set `a:b:c`, sets
            `a:b` and `a` must also be included).
        """
        # This provider does not use sets.
        return []

    def get_record(self, identifier, metadata_prefix):
        """
        Fetch the metadata of an item.

        Parameters
        ----------
        identifier: unicode
            The OAI identifier (as returned by identifiers()) of the item.
        metadata_prefix: unicode
            The metadata prefix (as returned by formats()) of the format.

        Return
        ------
        str or NoneType:
            An XML fragment containing the metadata of the item in the
            given format. If the format is not available for the item
            return `None`.

        Raises
        ------
        Exception:
            If converting or reading the metadata fails.
        """
        if metadata_prefix != 'oai_dc':
            return None

        filename = self.get_filename(identifier)
        path = os.path.join(self.directory, filename)
        with open(path, 'r') as file_:
            xmltree = etree.parse(file_)
        return etree.tostring(convert_to_dc(xmltree))

    def make_identifier(self, filename):
        """
        Form an OAI identifier for the given file.
        """
        # Remove the ".xml" extension from filename.
        filename = filename[len(self.directory) + 1:-4]
        return self.oai_identifier_prefix + filename

    def get_filename(self, identifier):
        """
        Extract the filename from an OAI identifier.
        """
        if not identifier.startswith(self.oai_identifier_prefix):
            raise ValueError('invalid identifier')
        return identifier[len(self.oai_identifier_prefix):] + '.xml'


def convert_to_dc(record):
    # Namespaces.
    nsmap = {
        'oai_dc': 'http://www.openarchives.org/OAI/2.0/oai_dc/',
        'dc': 'http://purl.org/dc/elements/1.1/',
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
    }

    # Mapping from DDI Version 2 to Dublin Core
    # (http://www.ddialliance.org/resources/tools/dc).
    mapping = {
        'title': ['stdyDscr/citation/titlStmt/titl'],
        'creator': ['stdyDscr/citation/rspStmt/AuthEnty'],
        'subject': [
            'stdyDscr/stdyInfo/subject/keyword',
            'stdyDscr/stdyInfo/subject/topcClas',
        ],
        'description': ['stdyDscr/stdyInfo/abstract/p'],
        'publisher': ['stdyDscr/citation/prodStmt/producer'],
        'contributor': ['stdyDscr/citation/rspStmt/othId/p'],
        'date': ['stdyDscr/citation/prodStmt/prodDate'],
        'type': ['stdyDscr/stdyInfo/sumDscr/dataKind'],
        'format': ['fileDscr/fileTxt/fileType'],
        'identifier': ['stdyDscr/citation/titlStmt/IDNo'],
        'source': ['stdyDscr/method/dataColl/sources/dataSrc'],
        'language': [],
        'relation': [
            'stdyDscr/othrStdyMat/relMat',
            'stdyDscr/othrStdyMat/relStdy',
            'stdyDscr/othrStdyMat/relPubl',
        ],
        'coverage': [
            'stdyDscr/stdyInfo/sumDscr/timePrd',
            'stdyDscr/stdyInfo/sumDscr/collDate',
            'stdyDscr/stdyInfo/sumDscr/nation',
            'stdyDscr/stdyInfo/sumDscr/geogCover',
        ],
        'rights': ['stdyDscr/citation/prodStmt/copyright'],
    }

    root = etree.Element('{{{oai_dc}}}dc'.format(**nsmap), nsmap=nsmap)
    root.set('{{{xsi}}}schemaLocation'.format(**nsmap),
        ('http://www.openarchives.org/OAI/2.0/oai_dc/ '
         'http://www.openarchives.org/OAI/2.0/oai_dc.xsd')
    )

    def add_field(name, text):
        """Add a field to the DC XML tree."""
        if text is not None and len(text) > 0 and not text.isspace():
            element = root.makeelement(
                '{{{dc}}}{name}'.format(name=name, **nsmap)
            )
            element.text = text
            root.append(element)

    for dc_tag, ddi_paths in mapping.iteritems():
        for ddi_path in ddi_paths:
            for element in record.findall(ddi_path):
                add_field(dc_tag, element.text)

    return root
