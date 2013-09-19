#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging

from optparse import OptionParser

_L=logging.getLogger(__name__)

from django.conf import settings

def makeParser():
    P = OptionParser()
    P.add_option('-v', '--verbose', action='count', default=0)
    P.add_option('-q', '--quiet', action='store_true', default=False)

    P.add_option('-O', '--outdir', metavar='DIR', default='..',
                 help='The directory into which expanded template files will be written')
    P.add_option('-D', '--define', metavar='KEY=VAL', default=[], dest='macros', action='append',
                 help='Add definitions to the template context')

    P.add_option('-P', '--period',
                 metavar='TIME', type='float', default=0.0,
                 help='When period > 0, template files are periodically re-expanded')

    P.add_option('-T', '--timeout',
                 metavar='TIME', type='float', default=5.0,
                 help='CA operation timeout.  Must be less than period (if given)')
    P.add_option('', '--no-dbe-prop', action='store_false', default=True, dest='useprop',
                 help="Do not request DBE_PROPERTY.  Causes problems with CA Gateway")
    return P.parse_args()


def expand(files, dict):
    import django.template.loader as loader
    from django.http import HttpRequest
    from django.template.context import RequestContext
    for F in files:
        R = HttpRequest()
        R.path = F
        R.method = 'GET'
        _L.debug('Expand %s', F)
        print loader.render_to_string(F, {}, RequestContext(R, dict))

def main():
    opts, files = makeParser()

    if opts.quiet:
        LVL = logging.ERROR
    else:
        # map 0..3
        # onto
        # WARN..DEBUG
        LVL = logging.WARN - 10*opts.verbose
    logging.basicConfig(level=LVL)

    M = {}
    for P in opts.macros:
        K,_,V = P.partition('=')
        V = V or ''
        K, V = K.strip(), V.strip()
        if K:
            M[K] = V

    S={'CAJ_OP':'GET',
       'CAJ_TIMEOUT':opts.timeout,
       'CAJ_USE_DBE_PROP':opts.useprop,
       'INSTALLED_APPS':['cajango'],
       'TEMPLATE_DIRS':['.'],
       'TEMPLATE_DEBUG':True,
       }
    if opts.period>0:
        S['CAJ_OP'] = 'MONITOR'
        if opts.period<=opts.timeout:
            opts.timeout = opts.period/2.0
            _L.warn('timeout must be < period.  Using %f', opts.timeout)

    settings.configure(**S)

    _L.info('Initial expansion')
    expand(files, M)
    _L.info('Initial expansion complete')

    if opts.period>0:
        import cajango.templatetags.cajango as caj
        import cothread
        try:
            while True:
                caj.anychange.Wait()
                _L.info('re-expansion')
                expand(files, M)
                _L.info('re-expansion complete')
                cothread.Sleep(opts.period)
        except KeyboardInterrupt:
            pass

    _L.info('Done')

if __name__=='__main__':
    main()
