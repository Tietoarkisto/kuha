import sys

from pyramid.config import Configurator
from pyramid.paster import setup_logging

from ..config import clean_oai_settings
from ..models import create_engine, ensure_oai_dc_exists

def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    clean_oai_settings(settings)

    setup_logging(settings['logging_config'])
    create_engine(settings)
    ensure_oai_dc_exists()

    config = Configurator(settings=settings)
    config.include('pyramid_tm')
    config.include('pyramid_chameleon')
    config.add_route('oai', '/oai', request_method=('GET', 'POST'))
    config.scan()
    return config.make_wsgi_app()
