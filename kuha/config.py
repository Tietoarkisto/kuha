import re

from lxml import etree
from pyramid.settings import asbool

from .exception import ConfigurationError

def clean_oai_settings(settings):
    """Parse and validate OAI app settings in a dictionary.

    Check that the settings required by the OAI app are in the settings
    dictionary and have valid values. Convert them to correct types.
    Required settings are:
        admin_emails
        deleted_records
        item_list_limit
        logging_config
        repository_descriptions
        repository_name
        sqlalchemy.url

    Parameters
    ----------
    settings: dict from str to str
        The settings dictionary.

    Raises
    ------
    ConfigurationError:
        If some setting is missing or has an invalid value.
    """
    cleaners = {
        'admin_emails': _clean_admin_emails,
        'deleted_records': _clean_deleted_records,
        'item_list_limit': _clean_item_list_limit,
        'logging_config': _clean_unicode,
        'repository_descriptions': _load_repository_descriptions,
        'repository_name': _clean_unicode,
        'sqlalchemy.url': _clean_unicode,
    }
    _clean_settings(settings, cleaners)


def clean_importer_settings(settings):
    """Parse and validate metadata importer settings in a dictionary.

    Check that the settings required by the metadata importer are in the
    settings dictionary and have valid values. Convert them to correct
    types. Required settings are:
        deleted_records
        force_update
        logging_config
        sqlalchemy.url
        timestamp_file
        metadata_provider_class
        metadata_provider_args

    Parameters
    ----------
    settings: dict from str to str
        The settings dictionary.

    Raises
    ------
    ConfigurationError:
        If some setting is missing or has an invalid value.
    """
    cleaners = {
        'deleted_records': _clean_deleted_records,
        'force_update': _clean_force_update,
        'logging_config': _clean_unicode,
        'sqlalchemy.url': _clean_unicode,
        'timestamp_file': _clean_unicode,
        'metadata_provider_args': _clean_unicode,
        'metadata_provider_class': _clean_provider_class,
    }
    return _clean_settings(settings, cleaners)


def _clean_settings(settings, cleaners):
    """Check that settings are ok.

    The parameter `cleaners` is a dict from setting names to functions.
    Each cleaner function is called with the value of the corresponding
    setting. The cleaners should raise an exception if the value is invalid
    and otherwise return a cleaned value. The old value gets replaced by
    the cleaned value.

    Parameters
    ----------
    settings: dict from str to str
        The settings dictionary.
    cleaners: dict from str to callable
        Mapping from setting names to cleaner functions.

    Raises
    ------
    ConfigurationError:
        If any setting is missing or invalid.
    """
    for name, func in cleaners.iteritems():
        if name not in settings:
            raise ConfigurationError('missing setting {0}'.format(name))

        try:
            cleaned = func(settings[name])
            settings[name] = cleaned
        except Exception as error:
            raise ConfigurationError(
                'invalid {0} setting: {1}'.format(name, error)
            )


def _clean_admin_emails(value):
    """Check that the value is a list of valid email addresses."""
    # email regex pattern defined in the OAI-PMH XML schema
    pattern = re.compile(r'^\S+@(\S+\.)+\S+$', flags=re.UNICODE)

    emails = _clean_unicode(value).split()
    if not emails:
        raise ValueError('no emails')
    for email in emails:
        if re.match(pattern, email) is None:
            raise ValueError(
                'invalid email address: {0}'
                ''.format(repr(email))
            )
    return emails


def _clean_deleted_records(value):
    """Check that value is one of "no", "transient", "persistent"."""
    allowed_values = ['no', 'transient', 'persistent']
    if value not in allowed_values:
        raise ValueError('deleted_records must be one of {0}'.format(
            allowed_values
        ))
    return unicode(value)


def _clean_force_update(value):
    """Return the value as a bool."""
    return asbool(value)


def _clean_item_list_limit(value):
    """Check that value is a positive integer."""
    int_value = int(value)
    if int_value <= 0:
        raise ValueError('item_list_limit must be positive')
    return int_value


def _clean_unicode(value):
    """Return the value as a unicode."""
    if isinstance(value, str):
        return value.decode('utf-8')
    else:
        return unicode(value)


def _clean_provider_class(value):
    """Split the value to module name and classname."""
    modulename, classname = value.split(':')
    if len(modulename) == 0:
        raise ValueError('empty module name')
    if len(classname) == 0:
        raise ValueError('empty class name')
    return (modulename, classname)


def _load_repository_descriptions(value):
    """Load XML fragments from files."""

    def load_description(path):
        """Load a single description."""
        with open(path, 'r') as file_:
            contents = file_.read()

        try:
            doc = etree.fromstring(contents.encode('utf-8'))
        except Exception as error:
            raise ValueError(
                'ill-formed XML in repository description {0}: '
                '{1}'.format(repr(path), error)
            )

        xsi_ns = 'http://www.w3.org/2001/XMLSchema-instance'
        if doc.get('{{{0}}}schemaLocation'.format(xsi_ns)) is None:
            raise ValueError('no schema location')

        return contents

    paths = value.split()
    return map(load_description, paths)
