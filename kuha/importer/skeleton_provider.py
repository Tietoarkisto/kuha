class SkeletonProvider(object):
    """
    Provider 
    """

    def __init__(self, *args):
        """
        Initialize the metadata provider.

        Parameters
        ----------
        args:
            Arguments given in the config file.
        """

    def formats(self):
        """
        List the available metadata formats.

        Return
        ------
        dict from unicode to (unicode, unicode):
            Mapping from metadata prefixes to (namespace, schema location)
            tuples.
        """
        # NOTE: The OAI DC format is required by the OAI-PMH specification.
        return {
            u'oai_dc': (u'http://www.openarchives.org/OAI/2.0/oai_dc/',
                        u'http://www.openarchives.org/OAI/2.0/oai_dc.xsd'),
        }

    def identifiers(self):
        """
        List all identifiers.

        Return
        ------
        iterable of unicode:
            OAI identifiers of all items
        """
        return [u'oai:example.org:123']

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
        return False

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
        return [(u'example',         u'Example Set'),
                (u'example:example', u'Example Subset')]

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
        return '''
            <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
                       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                       xmlns:dc="http://purl.org/dc/elements/1.1/"
                       xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/oai_dc/
                                           http://www.openarchives.org/OAI/2.0/oai_dc.xsd">
                <dc:title>Example Record</dc:title>
            </oai_dc:dc>
        '''
