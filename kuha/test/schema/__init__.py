import os

from lxml import etree

# the master schema will be stored here after it is loaded
_the_schema = None

def master_schema():
    """Return the master XSD schema.

    The master schema contains schemas for OAI-PMH responses and
    the OAI DC metadata format.

    Return
    ------
    lxml.etree.XMLSchema
        The schema.
    """
    global _the_schema
    if _the_schema is None:
        schema_path = os.path.join(__path__[0], 'master.xsd')
        _the_schema = etree.XMLSchema(file=schema_path)
    return _the_schema
