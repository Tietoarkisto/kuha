import datetime


def datestamp_now():
    """Create a datestamp of the current time at second granularity.

    Return
    ------
    datetime.datetime:
        Current time.
    """
    now = datetime.datetime.utcnow()
    # Strip microseconds.
    return now.replace(microsecond=0)


def format_datestamp(datestamp):
    """Format datestamp to an OAI-PMH compliant format.

    Parameters
    ----------
    datestamp: datetime.datetime
        A datestamp.

    Return
    ------
    str:
        Formatted datestamp.
    """
    return datestamp.strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_date(text, default_time=datetime.time(0, 0, 0)):
    """Parse a datestamp.

    Parameters
    ----------
    text: str
        Datestamp to parse. Format of the datestamp must be either
        YYYY-MM-DD or YYYY-MM-DDThh:mm:ssZ.
    default_time: datetime.time
        Hours, minutes and seconds that will be used when the datestamp is
        in format YYYY-MM-DD.

    Raises
    ------
    ValueError:
        If the text is in invalid format.

    Return
    ------
    datetime.datetime:
        The parsed date.
    datetime.timedelta:
        Granularity of the parsed date. Either timedelta(1) or
        timedelta(0, 0, 1).
    """
    if len(text) == len('YYYY-MM-DDTHH:MM:SSZ'):
        datestamp = datetime.datetime.strptime(
            text, '%Y-%m-%dT%H:%M:%SZ')
        return datestamp, datetime.timedelta(0, 0, 1)

    elif len(text) == len('YYYY-MM-DD'):
        date = datetime.datetime.strptime(text, '%Y-%m-%d')
        return date.replace(
            hour=default_time.hour,
            minute=default_time.minute,
            second=default_time.second,
        ), datetime.timedelta(1)

    else:
        raise ValueError('unsupported date format')
