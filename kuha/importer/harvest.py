import logging

from .. import models
from ..exception import HarvestError

def update(provider, since=None, purge=False, dry_run=False):
    """Update metadata formats, items, records and sets.

    Parameters
    ----------
    provider: object
        The metadata provider. Must have the following methods:

            formats(): dict from unicode to (unicode, unicode)
                The available metadata formats as a dict mapping metadata
                prefixes to (namespace, schema location) tuples.

            identifiers(): iterable of unicode
                OAI identifiers of all items.

            has_changed(identifier: unicode, since: datetime): bool
                Return `True` if the item with the given identifier has
                changed since the given time. Otherwise return `False`.

            get_sets(identifier: unicode): iterable of (unicode, unicode)
                Return sets of the item with the given identifier as an
                iterable of (set spec, set name) tuples.

            get_record(identifier: unicode, prefix: unicode):
                    unicode or None
                Disseminate the metadata of the specified item in the
                specified format. Return an XML fragment. If the item
                cannot be disseminated in the specified format, return
                None.

    since: datetime.datetime or None
        Time of the last update in UTC, or `None`.
    purge: bool
        If `True`, purge deleted formats, items and records from the
        database.
    dry_run: bool
        If `True`, fetch records as usual but do not actually change the
        database.

    Raises
    ------
    HarvestError:
        If the provider raises an exception and the harvest cannot be
        continued.
    """
    prefixes = update_formats(provider, purge, dry_run)
    identifiers = update_items(provider, purge, dry_run)
    update_records(provider, identifiers, prefixes, since, dry_run)


def update_formats(provider, purge=False, dry_run=False):
    log = logging.getLogger(__name__)
    log.debug('Updating metadata formats...')

    try:
        new_formats = provider.formats()

        if len(new_formats) == 0:
            raise ValueError('no formats')

        old_formats = dict(
            (format_.prefix, format_)
            for format_ in models.Format.list(ignore_deleted=True)
        )

        removed = 0
        for prefix, format_ in old_formats.iteritems():
            if prefix not in new_formats:
                if not dry_run:
                    format_.mark_as_deleted()
                removed += 1

        added = 0
        for prefix, (namespace, schema) in new_formats.iteritems():
            if not dry_run:
                models.Format.create_or_update(prefix, namespace, schema)
            if prefix not in old_formats:
                added += 1

        if purge and not dry_run:
            models.purge_deleted()
    except Exception as e:
        models.rollback()
        log.exception('Failed to update metadata formats: {0}'.format(e))
        raise HarvestError(e.message)

    else:
        if dry_run:
            models.rollback()
        else:
            models.commit()
        # TODO: log number of changed formats
        log.info(
            'Removed {0} format{1} and added {2} format{3}.'
            ''.format(
                removed, '' if removed == 1 else 's',
                added,   '' if added   == 1 else 's',
            )
        )

        return new_formats.keys()


def update_items(provider, purge=False, dry_run=False):
    log = logging.getLogger(__name__)
    log.debug('Looking for added and removed items...')

    try:
        new_identifiers = frozenset(map(unicode, provider.identifiers()))

        old_items = dict(
            (item.identifier, item)
            for item in models.Item.list(ignore_deleted=True)
        )

        removed = 0
        for identifier, item in old_items.iteritems():
            if identifier not in new_identifiers:
                if not dry_run:
                    item.mark_as_deleted()
                log.debug('deleted {0}'.format(identifier))
                removed += 1

        added = 0
        for identifier in new_identifiers:
            if not dry_run:
                models.Item.create_or_update(identifier)
            if identifier not in old_items:
                log.debug('added {0}'.format(identifier))
                added += 1

        if purge and not dry_run:
            models.purge_deleted()
    except Exception as e:
        models.rollback()
        log.exception('Failed to update items: {0}'.format(e))
        raise HarvestError(e.message)
    else:
        if dry_run:
            models.rollback()
        else:
            models.commit()
        log.info(
            'Removed {0} item{1} and added {2} item{3}.'
            ''.format(
                removed, '' if removed == 1 else 's',
                added,   '' if added   == 1 else 's',
            )
        )

        return new_identifiers


def update_sets(provider, identifier, dry_run=False):
    log = logging.getLogger(__name__)
    log.debug('Updating sets...')

    # Remove the item from old sets.
    item = None
    if not dry_run:
        item = models.Item.get(identifier)
        item.clear_sets()

    sets = provider.get_sets(identifier)
    if len(sets) == 0:
        return
    # Sort set specs by level.
    sets.sort(key=lambda (spec, _): spec.count(u':'))
    # TODO: make sure that sets contain the parent sets of all sets
    for spec, name in sets:
        if not dry_run:
            set_ = models.Set.create_or_update(spec, name)
            item.add_to_set(set_)


def update_records(provider,
                   identifiers,
                   prefixes,
                   since=None,
                   dry_run=False):
    log = logging.getLogger(__name__)
    if since is not None:
        log.info('Updating records modified since {0} UTC...'
                 ''.format(since))
    else:
        log.info('Updating all records...')

    updated = 0
    for identifier in identifiers:
        try:
            if (since is not None and
                    not provider.has_changed(identifier, since)):
                log.debug('Skipping item "{0}"'.format(identifier))
                continue
            log.debug('Updating item "{0}"'.format(identifier))

            update_sets(provider, identifier, dry_run)
        except Exception as e:
            log.exception(
                'Failed to update item "{0}": {1}'
                ''.format(identifier, e))
            continue

        for prefix in prefixes:
            try:
                xml = provider.get_record(identifier, prefix)
                if xml is None:
                    if not dry_run:
                        models.Record.mark_as_deleted(identifier, prefix)
                else:
                    if not dry_run:
                        models.Record.create_or_update(
                            identifier, prefix, xml
                        )
                    updated += 1
            except Exception as e:
                models.rollback()
                log.exception(
                    'Failed to disseminate format "{0}" '
                    'for item "{1}": {2}'
                    ''.format(prefix, identifier, e))
            else:
                # Commit after each record so that the (esp. SQLite)
                # database does not get locked for a long time.
                if dry_run:
                    models.rollback()
                else:
                    models.commit()
                log.debug('Processed item "{0}"'.format(identifier))

    # End the transaction in case no records were updated.
    models.rollback()

    # TODO: log number of added records
    log.info('Updated {0} record{1}.'
             ''.format(updated, '' if updated == 1 else 's'))
