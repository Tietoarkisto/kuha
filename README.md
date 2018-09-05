
We're concentrating on Kuha2 nowdays, see https://bitbucket.org/account/user/tietoarkisto/projects/KUH


Kuha OAI-PMH Server
===================

Kuha is a lightweight [OAI-PMH][] Data Provider implementation. It
is written in Python with [The Pyramid Web Framework][Pyramid].

Features
--------
 * All six OAI-PMH verbs
 * Support for many optional features, including
    * Deleted records
    * Resumption tokens
    * Set hierarchies
 * DDI Codebook to Dublin Core crosswalk

Installation
------------
Set up a virtual environment (recommended).

```
$ virtualenv env
$ . env/bin/activate
```

Install the package and dependencies.

```
$ python setup.py install
```

Make a copy of the example configuration file and customize it. The
available settings are documented in the [example file](example.ini).

```
$ cp example.ini my_config.ini
$ vim my_config.ini
```

Kuha comes with a simple module for converting [DDI Codebook][] files to
unqualified [Dublin Core][]. You can configure Kuha to use this
module by settings the `metadata_provider_class` option to
`kuha.importer.ddi_file_provider:DdiFileProvider`. The module needs two
arguments: a domain name for the OAI identifier and a path of the
directory to scan. Set these in the `metadata_provider_args` setting.

Example:

```
# my_config.ini

metadata_provider_class =
   kuha.importer.ddi_file_provider:DdiFileProvider

metadata_provider_args =
   my.organization.org
   /srv/metadata

# ...
```

See [Extending](#extending) for help on writing your own metadata
provider.

Usage
-----
Run the metadata import.

```
$ kuha_import my_config.ini
```

Start the OAI-PMH serverk

```
$ pserve my_config.ini
```

With the example configuration, you can get the identify page at
<http://127.0.0.1:6543/oai?verb=Identify>.

Extending
---------
For most applications, a custom metadata provider is needed.
Metadata provider classes should implement an interface similar to
[`kuha.importer.skeleton_provider:SkeletonProvider`](kuha/importer/skeleton_provider.py)
and
[`kuha.importer.ddi_file_provider:DdiFileProvider`](kuha/importer/ddi_file_provider.py).
See comments in those files for details.

To make Kuha use your custom metadata provider, set the
`metadata_provider_class` setting to the Python name of the class
(e.g. `name.of.the.module:NameOfTheClass`). The value of the
`metadata_provider_args` setting is split at whitespace and the
resulting parts are passed to the constructor of the class.

[OAI-PMH]: http://www.openarchives.org/pmh/
           "Open Archives Initiative Protocol for Metadata Harvesting"

[Pyramid]: http://docs.pylonsproject.org/projects/pyramid/en/latest/index.html
           "The Pyramid Web Framework"

[DDI Codebook]: http://www.ddialliance.org/Specification/DDI-Codebook/
                "DDI Codebook"

[Dublin Core]: http://dublincore.org/documents/dces/
               "Dublin Core Metadata Element Set"
