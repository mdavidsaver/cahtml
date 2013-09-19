#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging, re, os, sys

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

# tokenize string.
# (quoted string, seperator, token)
_tokstr = re.compile(r'"(.*?)(?<!\\)"|([=,])|([^",=]+)')

def splitMac(s):
    macs={}
    key=None
    needval=False
    val=None

    for M in _tokstr.finditer(s):
        Q, S, T = M.groups()

        if Q:
            Q = re.sub(r'\\(.)', r'\1', Q) # unescape body of quoted string

        if not key:
            # macro name must be token
            if not T:
                raise RuntimeError('expected token at %d of "%s"'%(M.start(), s))
            key = T

        elif S=='=':
            # expect a value
            needval=True

        elif S==',':
            # end of macro def, store entry
            macs[key]=val
            key = val = None
            needval = False

        elif not S:
            # value token
            if not needval:
                raise RuntimeError('expected seperator at %d of "%s"'%(M.start(), s))
            if val: # append to existing value 'A=B"C"'
                val = val + (Q or T)
            else:
                val = Q or T

        else:
            raise RuntimeError('internal error at %d of "%s"'%(M.start(), s))

        macs[key]=val

    return macs

_filesplit=re.compile(r'(?<!\\):')

def splitFile(name):
    S = _filesplit.split(name, maxsplit=1)
    name = S[0]
    macents = None
    if len(S)>1:
        macents = splitMac(S[1])
    return (name, macents)

def expand(files, dict):
    import django.template.loader as loader
    from django.http import HttpRequest
    from django.template.context import RequestContext
    for F, M in files:
        R = HttpRequest()
        R.path = F
        R.method = 'GET'
        C = RequestContext(R, dict)
        C.update(M or {})
        _L.debug('Expand %s with %s', F, C)
        print loader.render_to_string(F, {}, C)

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

    # build global macro dict
    M = {}
    for P in opts.macros:
        K,_,V = P.partition('=')
        V = V or ''
        K, V = K.strip(), V.strip()
        if K:
            M[K] = V

    if 'DJANGO_SETTINGS_MODULE' not in os.environ:
        # No user supplied configuration
        S={'CAJ_OP':'GET',
           'CAJ_TIMEOUT':opts.timeout,
           'CAJ_PERIOD':opts.period,
           'CAJ_USE_DBE_PROP':opts.useprop,
           'INSTALLED_APPS':['cajango'],
           'TEMPLATE_DIRS':['.'],
           'TEMPLATE_DEBUG':True,
           }
        if opts.period>0:
            S['CAJ_OP'] = 'MONITOR'
        settings.configure(**S)

    else:
        # validate user config
        opts.period = settings.CAJ_PERIOD
        opts.timeout = settings.CAJ_TIMEOUT
        if settings.CAJ_OP=='MONITOR' and opts.period<=0:
            opts.period = 60.0
            _L.warn('Using default MONITOR period of %f sec', opts.period)
        if 'cajango' not in settings.INSTALLED_APPS:
            _L.error('custom configuration must include \'cajango\' in INSTALL_APPS')
            sys.exit(1)

    if opts.period<=opts.timeout:
        opts.timeout = opts.period/2.0
        _L.warn('timeout must be < period.  Using %f', opts.timeout)

    files = filter(lambda a:a, map(splitFile, files))

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
