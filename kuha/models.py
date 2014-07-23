import logging
import re

from lxml import etree
import sqlalchemy as sa
import sqlalchemy.orm as orm
from sqlalchemy.ext.declarative import declarative_base
import transaction
from zope.sqlalchemy import ZopeTransactionExtension

from .util import datestamp_now

_Base = declarative_base()
DBSession = orm.scoped_session(orm.sessionmaker(
    extension=ZopeTransactionExtension()
))


class _CreateMixin(object):

    @classmethod
    def create(cls, *args, **kwargs):
        """Create an object and add it to the database."""
        obj = cls(*args, **kwargs)
        DBSession.add(obj)
        return obj


def create_engine(settings):
    """Connect to the database."""
    engine = sa.engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)
    _Base.metadata.bind = engine
    _Base.metadata.create_all(engine)


def ensure_oai_dc_exists():
    """Add the OAI DC format to the database if it does not exist."""
    if not Format.exists('oai_dc'):
        Format.create('oai_dc',
                      'http://www.openarchives.org/OAI/2.0/oai_dc/',
                      'http://www.openarchives.org/OAI/2.0/oai_dc.xsd')
        commit()


def purge_deleted():
    """Remove items, records and formats marked as deleted."""
    purged = 0
    for Class in [Record, Format, Item]:
        purged += (DBSession.query(Class)
                            .filter(Class.deleted.is_(True))
                            .delete(synchronize_session='fetch'))
    if purged > 0:
        Datestamp.update()


def commit():
    """Commit the ongoing database transaction."""
    transaction.commit()


def rollback():
    """Roll back the ongoing database transaction."""
    transaction.abort()


item_set_association = sa.Table(
    'item_set_association',
    _Base.metadata,
    sa.Column(
        'set_spec',
        sa.String,
        sa.ForeignKey('sets.spec')
    ),
    sa.Column(
        'item_identifier',
        sa.String,
        sa.ForeignKey('items.identifier')
    ),
)


class Set(_Base, _CreateMixin):
    """The SQLAlchemy model class for an OAI set."""
    __tablename__ = 'sets'
    spec = sa.Column(sa.String, primary_key=True)
    name = sa.Column(sa.String, nullable=False)

    # the pattern of valid set specs from the OAI-PMH XML schema
    _spec_pattern = re.compile(
        "^([A-Za-z0-9\-_\.!~\*'\(\)])+(:[A-Za-z0-9\-_\.!~\*'\(\)]+)*$")

    def __init__(self, spec, name):
        if self._spec_pattern.match(spec) is None:
            raise ValueError('invalid set spec: {0}'.format(spec))
        # TODO: check that all parent sets exist
        self.spec = spec
        self.name = name

    def update(self, name):
        """Change the name of this set."""
        self.name = name

    @classmethod
    def create_or_update(cls, spec, name):
        """Add a Set to the database or change name of an existing one.

        Return
        ------
        Set:
            The created or updated Set.
        """
        try:
            set_ = DBSession.query(cls).filter_by(spec=spec).one()
        except orm.exc.NoResultFound:
            return cls.create(spec, name)
        else:
            set_.name = name
            return set_

    @classmethod
    def list(cls):
        return DBSession.query(cls).all()


class Format(_Base, _CreateMixin):
    """The SQLAlchemy model class for an OAI metadata format."""
    __tablename__ = 'formats'
    prefix = sa.Column(sa.String, primary_key=True)
    namespace = sa.Column(sa.String, nullable=False)
    schema = sa.Column(sa.String, nullable=False)
    deleted = sa.Column(sa.Boolean, nullable=False)

    # Function to find characters that are not URL unreserved.
    _invalid_characters = re.compile(r'[^a-zA-Z0-9\-_.!~*\'()]').search

    def __init__(self, prefix, namespace, schema):
        if self._invalid_characters(prefix) is not None:
            raise ValueError('invalid metadata prefix: %s' % prefix)

        self.prefix = prefix
        self.namespace = namespace
        self.schema = schema
        self.deleted = False

    @classmethod
    def exists(cls, prefix, ignore_deleted=False):
        """Check wheter a metadata format is supported.

        Parameters
        ----------
        prefix: unicode
            A metadata prefix.
        ignore_deleted: bool
            If `True`, consider deleted formats as not existing.

        Return
        ------
        bool:
            ``True`` if the metadata format is supported, ``False``
            otherwise.
        """
        query = DBSession.query(cls).filter_by(prefix=prefix)
        if ignore_deleted:
            query = query.filter(cls.deleted.is_(False))
        try:
            query.one()
            return True
        except orm.exc.NoResultFound:
            return False

    @classmethod
    def list(cls, identifier=None, ignore_deleted=False):
        """Return available metadata formats.

        If ``identifier`` is given, return metadata formats available for
        that item. Otherwise return all supported metadata formats.

        Parameters
        ----------
        identifier: unicode or None
            Identifier of the item.
        ignore_deleted: bool
            If `True`, exclude deleted formats from the result.

        Return
        ------
        list of Format:
            The available metadata formats.
        """
        query = DBSession.query(cls)
        if identifier is not None:
            subquery = DBSession.query(Record).filter_by(
                identifier=identifier,
                prefix=cls.prefix,
            )
            if ignore_deleted:
                subquery = subquery.filter(Record.deleted.is_(False))
            query = query.filter(subquery.exists())
        if ignore_deleted:
            query = query.filter(cls.deleted.is_(False))
        return query.all()

    def update(self, namespace, schema):
        """Change the namespace and schema of this format."""
        if self.namespace != namespace or self.schema != schema:
            # Since the format has changed, the xml data of the
            # associated records might no longer be valid. Mark
            # them as deleted.
            self.mark_as_deleted()

        self.namespace = namespace
        self.schema = schema
        self.deleted = False
        # The associated records must be left deleted even if the
        # format was not changed.

    @classmethod
    def create_or_update(cls, prefix, namespace, schema):
        """Add a Format to the database or update an existing one.

        Return
        ------
        Format:
            The created or updated Format.

        Raises
        ------
        ValueError:
            If the prefix, namespace or schema is not valid.
        """
        try:
            format_ = (DBSession.query(cls)
                                .filter_by(prefix=prefix)
                                .one())
        except orm.exc.NoResultFound:
            return cls.create(prefix, namespace, schema)
        else:
            format_.update(namespace, schema)
            return format_

    def mark_as_deleted(self):
        """Mark this format and associated records as deleted."""
        Record.mark_as_deleted(prefix=self.prefix)
        self.deleted = True


class Item(_Base, _CreateMixin):
    """The SQLAlchemy model class for an OAI item."""
    __tablename__ = 'items'
    identifier = sa.Column(sa.String, primary_key=True)
    deleted = sa.Column(sa.Boolean, nullable=False)

    sets = orm.relationship('Set', secondary=item_set_association)

    def __init__(self, identifier):
        self.identifier = identifier
        self.deleted = False

    def clear_sets(self):
        self.sets = []

    def add_to_set(self, set_):
        self.sets.append(set_)

    @classmethod
    def get(cls, identifier):
        return DBSession.query(cls).filter_by(identifier=identifier).one()

    @classmethod
    def create_or_update(cls, identifier):
        """Add an Item to the database or undelete an existing one.

        Return
        ------
        Item:
            The created or updated Item.
        """
        try:
            item = cls.get(identifier)
        except orm.exc.NoResultFound:
            return cls.create(identifier)
        else:
            item.deleted = False
            return item

    @classmethod
    def exists(cls, identifier, ignore_deleted=False):
        """Check wheter an item exists.

        Parameters
        ----------
        identifier: unicode
            An OAI identifier URI.
        ignore_deleted: bool
            If `True`, consider deleted identifiers as not existing.

        Return
        ------
        bool:
            ``True`` if an item with the identifier exists, ``False``
            otherwise.
        """
        query = DBSession.query(cls).filter_by(identifier=identifier)
        if ignore_deleted:
            query = query.filter(cls.deleted.is_(False))
        try:
            query.one()
            return True
        except orm.exc.NoResultFound:
            return False

    @classmethod
    def list(cls, ignore_deleted=False):
        """Return all existing items.

        Parameters
        ----------
        ignore_deleted: bool
            If `True`, exclude deleted items from the result.

        Return
        ------
        list of Item:
            The available metadata formats.
        """
        query = DBSession.query(cls)
        if ignore_deleted:
            query = query.filter(cls.deleted.is_(False))
        return query.all()

    def mark_as_deleted(self):
        """Mark this item and associated records as deleted."""
        Record.mark_as_deleted(identifier=self.identifier)
        self.deleted = True


class Record(_Base, _CreateMixin):
    """The SQLAlchemy model class for an OAI record."""
    __tablename__ = 'records'
    identifier = sa.Column(
        sa.String,
        sa.ForeignKey('items.identifier'),
        primary_key=True
    )
    prefix = sa.Column(
        sa.String,
        sa.ForeignKey('formats.prefix'),
        primary_key=True
    )
    datestamp = sa.Column(sa.DateTime, nullable=False)
    xml = sa.Column(sa.Text)
    deleted = sa.Column(sa.Boolean, nullable=False)

    def __init__(self, identifier, prefix, xml, datestamp=None):
        try:
            format_ = (DBSession.query(Format)
                                .filter_by(prefix=prefix)
                                .one())
        except orm.exc.NoResultFound:
            raise ValueError(
                'non-existent metadata prefix: "{0}"'
                ''.format(prefix)
            )

        try:
            item = (DBSession.query(Item)
                             .filter_by(identifier=identifier)
                             .one())
        except orm.exc.NoResultFound:
            raise ValueError(
                'non-existent identifier: "{0}"'
                ''.format(identifier)
            )

        self.identifier = identifier
        self.prefix = prefix
        self.datestamp = (datestamp if datestamp is not None
                          else datestamp_now())
        self.xml = xml
        self.deleted = False

        if self.xml is not None:
            self._check_xml(self.xml, format_)

    @classmethod
    def earliest_datestamp(cls, ignore_deleted=False):
        """Fetch the earliest datestamp.

        Parameters
        ----------
        ignore_deleted: bool
            If `True`, return the earliest datestamp of a that is
            not deleted. Otherwise return the earliest datestamp of all
            records.

        Return
        ------
        datetime.datetime or None:
            The earliest datestamp. If there are no records in the
            database, return ``None``.
        """
        query = DBSession.query(cls.datestamp)
        if ignore_deleted:
            query = query.filter(cls.deleted.is_(False))
        result = query.order_by(cls.datestamp).first()

        if result is not None:
            # The query returns a 1-tuple.
            return result[0]
        return None

    @classmethod
    def list(cls,
             identifier=None,
             metadata_prefix=None,
             from_date=None,
             until_date=None,
             set_=None,
             ignore_deleted=False,
             offset=None,
             limit=None):
        """Return records that fulfill the conditions.

        Parameters
        ----------
        identifier: unicode or None
            Identifier of the item.
        metadata_prefix: unicode or None
            Prefix of the metadata format.
        from_date: datetime.datetime or None
            Minimum allowed datestamp.
        until_date: datetime.datetime or None
            Maximum allowed datestamp.
        set_: unicode or None
            Set spec of the item.
        ignore_deleted: bool
            If `True`, exclude deleted records from the result.
        offset: unicode or None
            Minimum allowed identifier.
        limit: int or None
            Maxmimum number of results.

        Return
        ------
        list of Record:
            The matching records. If no records match, an empty list is
            returned.
        """
        query = DBSession.query(cls)

        if identifier is not None:
            query = query.filter_by(identifier=identifier)
        if metadata_prefix is not None:
            query = query.filter_by(prefix=metadata_prefix)
        if from_date is not None:
            query = query.filter(cls.datestamp >= from_date)
        if until_date is not None:
            query = query.filter(cls.datestamp <= until_date)
        if ignore_deleted:
            query = query.filter(cls.deleted.is_(False))
        if set_ is not None:
            query = (query.join(Item).join(Item.sets)
                          .filter(Set.spec==set_))

        query = query.order_by(cls.identifier)

        if offset is not None:
            query = query.filter(cls.identifier >= offset)
        if limit is not None:
            if limit < 0:
                raise ValueError('negative limit: %d' % limit)
            query = query.limit(limit)

        return query.all()

    @classmethod
    def create(cls, *args, **kwargs):
        # Override create() to update the database datestamp.
        obj = super(Record, cls).create(*args, **kwargs)
        Datestamp.update()
        return obj

    def update(self, xml):
        """Change the XML data of this record."""
        if self.deleted or self.xml != xml:
            # Check the data.
            format_ = (DBSession.query(Format)
                                .filter_by(prefix=self.prefix)
                                .one())
            self._check_xml(xml, format_)

            self.xml = xml
            self.deleted = False
            self.datestamp = datestamp_now()
            Datestamp.update()

    @property
    def set_specs(self):
        """Return a list of specs for sets which contain this record.

        Sets which are parent sets of sets that contain the record are
        excluded from the result.
        """
        result = []
        # Fetch all set specs.
        specs = (DBSession.query(Set.spec).join(Item.sets)
                          .filter(Item.identifier==self.identifier)
                          .all())
        specs = [s for (s,) in specs]
        # Sort to descending order by level.
        specs.sort(key=lambda x: -x.count(':'))
        # A set containing the specs of sets whose subsets have already
        # been processed.
        processed = set()
        for spec in specs:
            if spec not in processed:
                result.append(spec)
                # Mark all parent sets of the set as processed.
                i = 0
                try:
                    while True:
                        i = spec.index(':', i)
                        processed.add(spec[:i])
                        i += 1
                except ValueError:
                    pass
        return result

    @classmethod
    def create_or_update(cls, identifier, prefix, xml):
        """Add a Record to the database or update an existing one.

        Try to find the Record by the identifier and prefix. If no Record
        is found, create a new one.

        Return
        ------
        Record:
            The created or updated Record.

        Raises
        ------
        ValueError:
            If some value is not valid.
        """
        try:
            record = (DBSession.query(cls)
                               .filter_by(identifier=identifier,
                                          prefix=prefix)
                               .one())
        except orm.exc.NoResultFound:
            return cls.create(identifier, prefix, xml)
        else:
            record.update(xml)
            return record

    @classmethod
    def mark_as_deleted(cls, identifier=None, prefix=None):
        """Mark records matching the identifier and prefix as deleted."""
        query = DBSession.query(cls)
        if identifier is not None:
            query = query.filter_by(identifier=identifier)
        if prefix is not None:
            query = query.filter_by(prefix=prefix)
        query = query.filter(cls.deleted.is_(False))
        updated = query.update(
            {'deleted': True, 'datestamp': datestamp_now()},
            synchronize_session='fetch'
        )
        if updated > 0:
            Datestamp.update()

    def _check_xml(self, xml, format_):
        # Check that the xml is well-formed.
        tree = etree.fromstring(xml)

        if etree.QName(tree.tag).namespace != format_.namespace:
            raise ValueError('wrong xml namespace')

        # Check that the xml has the correct schema location.
        xml_schemas = tree.get(
            '{http://www.w3.org/2001/XMLSchema-instance}schemaLocation'
        )
        if xml_schemas is None:
            raise ValueError('no schema location')

        for s in xml_schemas.split():
            if s == format_.schema:
                break
        else:
            raise ValueError('wrong schema location')


class Datestamp(_Base, _CreateMixin):
    """The SQLAlchemy model class for the datestamp of the database."""
    __tablename__ = 'datestamp'
    datestamp = sa.Column(sa.DateTime, primary_key=True)

    def __init__(self, datestamp):
        self.datestamp = datestamp

    @classmethod
    def get(cls):
        """Fetch the database modification datestamp.

        Return
        ------
        datetime.datetime or None:
            The datestamp of the latest database modification. If the
            database has never been modified, return None.
        """
        result = DBSession.query(cls.datestamp).first()
        if result is not None:
            # The query returns a 1-tuple.
            return result[0]
        return None

    @classmethod
    def update(cls):
        """Set the database datestamp to the current time."""
        try:
            datestamp = DBSession.query(cls).one()
            datestamp.datestamp = datestamp_now()
        except orm.exc.NoResultFound:
            DBSession.add(cls(datestamp_now()))
        except orm.exc.MultipleResultsFound:
            logging.getLogger(__name__).warning('Multiple datestamps')
            DBSession.query(cls).delete(synchronize_session='fetch')
            DBSession.add(cls(datestamp_now()))
