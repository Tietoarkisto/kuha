from ez_setup import use_setuptools
use_setuptools()

import os

from setuptools import setup, find_packages

if __name__ == '__main__':

    here = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(here, 'README.md')) as f:
        README = f.read()
    with open(os.path.join(here, 'CHANGES.txt')) as f:
        CHANGES = f.read()

    requires = [
        'lxml',
        'mock',
        'pyramid',
        'pyramid_chameleon',
        'pyramid_debugtoolbar',
        'pyramid_tm',
        'SQLAlchemy',
        'transaction',
        'waitress',
        'zope.sqlalchemy',
    ]

    setup(
        name='Kuha',
        version='0.0',
        description='An OAI-PMH Data Provider implementation',
        long_description=README + '\n\n' + CHANGES,
        classifiers=[
            "Programming Language :: Python",
            "Framework :: Pyramid",
            "Topic :: Internet :: WWW/HTTP",
            "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
        ],
        author='',
        author_email='',
        url='',
        keywords='web wsgi bfg pylons pyramid oai xml',
        packages=find_packages(),
        include_package_data=True,
        zip_safe=False,
        install_requires=requires,
        tests_require=requires,
        test_suite="kuha.test",
        entry_points={
            'paste.app_factory': [
                'main = kuha.oai:main',
            ],

            'console_scripts': [
                'kuha_import = kuha.importer:main',
            ],
        },
    )
