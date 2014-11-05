import logging
_L = logging.getLogger(__name__)

from datetime import datetime

from django import template
from django.conf import settings

from django.utils import safestring as ss

import cothread
import cothread.catools as ca
from cothread.cadef import ECA_DISCONN

register = template.Library()

MODE = getattr(settings, 'CAJ_OP', 'GET').upper()
TIMO = float(getattr(settings, 'CAJ_TIMEOUT', 5))
DBE_PROP = getattr(settings, 'CAJ_USE_DBE_PROP', True)

_pv_cache = {}

_name2fmt = {
    'RAW':ca.FORMAT_RAW,
    'TIME':ca.FORMAT_TIME,
    'CTRL':ca.FORMAT_CTRL,
    'GR':ca.FORMAT_CTRL,
}

_sevr2name = {0:'', 1:'Minor', 2:'Major', 3:'Invalid'}

_name2type = {}
for N in ['STRING','CHAR','SHORT','LONG','ENUM','FLOAT','DOUBLE','CHAR_STR']:
    _name2type[N] = getattr(ca, 'DBR_'+N)

anychange = cothread.Event()

class CAValueWrap(object):
    __value = None
    def __init__(self, val):
        self.__value = val

    @property
    def obj(self):
        "Access underlying catools value"
        return self.__value

    def __getattr__(self, name):
        "Delegate unknowns to the underlying value"
        assert name!='__value'
        return getattr(self.__value, name)

    @property
    def val(self):
        "Print the value as a string"
        V = self.__value
        return ss.EscapeUnicode(unicode(V if V.ok else None))

    @property
    def sevr(self):
        if not self.__value.ok:
            S = 'Disconnected'
        else:
            S = _sevr2name.get(self.__value.severity, 'Unknown')
        self.__value.sevr = S
        return S

    @property
    def time(self):
        if not self.__value.ok:
            T = 0
        else:
            T = self.__value.timestamp
        T = datetime.fromtimestamp(T)
        self.__value.time = T
        return T

    def span(self):
        if not self.__value.ok:
            S = 'Disconnected'
        else:
            S = _sevr2name.get(self.__value.severity, 'Unknown')
        return ss.SafeUnicode(u'<span class="caSevr%s">%s</span>'%
            (S, self.val))

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.val

if MODE=='GET':
    class CACache(object):
        def __init__(self, pv, **kws):
            self.name=u'CACache("%s",%s)'%(pv, kws)
            kws.pop('events',None)
            self.value = ca.caget(pv, timeout=TIMO, throw=False, **kws)
            _L.debug('caget %s -> %s', self.name, self.value)

    def __str__(self):
        return self.name

elif MODE=='MONITOR':
    class CACache(object):
        def __init__(self, pv, **kws):
            self.name=u'CACache("%s",%s)'%(pv, kws)
            _L.debug('camonitor %s', self.name)
            self.__S = ca.camonitor(pv, self.__update, notify_disconnect=True,
                                    **kws)
            self.value = ca.ca_nothing(pv, ECA_DISCONN)

        def __update(self, val):
            self.value = val

            if not val.ok:
                _L.debug('monitor disconnect "%s"', self.name)

            else:
                _L.debug('monitor update "%s"', self.name)

            anychange.Signal()

    def __str__(self):
        return self.name

else:
    raise ImportError("django setting CAJOP has invalid value '%s'"%MODE)

def expandName(context, pv):
    T = template.Template(pv)
    context.push()
    pv = T.render(context)
    context.pop()
    return pv.encode('ascii')

def getPV(pv, **kws):
    if not pv:
        raise template.TemplateSyntaxError("PV name can't be %s"%pv)

    try:
        F = kws['format']
    except KeyError:
        kws['format'] = ca.FORMAT_TIME
    else:
        kws['format'] = _name2fmt[F]

    try:
        D = kws['dtype']
        del kws['dtype']
    except KeyError:
        pass
    else:
        kws['datatype'] = _name2type[D]
    
    K = kws.items()
    K.sort()
    K = (pv, tuple(K))
    try:
        PV = _pv_cache[K]
    except KeyError:
        PV = CACache(pv, **kws)
        _pv_cache[K] = PV

    return CAValueWrap(PV.value)

# Fetch the value and render to a string
@register.simple_tag(takes_context=True)
def caget(context, pv, **kws):
    _L.debug('caget(ctxt, %s, %s)', pv, kws)
    pv = expandName(context, pv)
    val = getPV(pv, **kws)
    if val.ok and getattr(val, 'severity', 1)==0:
        return val.val
    else:
        return '%s: %s'%(val.sevr, val.val)

@register.simple_tag(takes_context=True)
def caspan(context, pv, default=u'No Conn', **kws):
    _L.debug('caspan(ctxt, %s, default=%s, %s)', pv, default, kws)
    pv = expandName(context, pv)
    kws.setdefault('dtype', 'STRING') # let the server handle formatting
    val = getPV(pv, **kws)
    return val.span()

@register.assignment_tag(takes_context=True)
def caval(context, pv, **kws):
    _L.debug('caval(ctxt, %s, %s)', pv, kws)
    pv = expandName(context, pv)
    return getPV(pv, **kws)

@register.assignment_tag(takes_context=True)
def cameta(context, pv, **kws):
    _L.debug('cameta(ctxt, %s, %s)', pv, kws)
    pv = expandName(context, pv)
    if DBE_PROP:
        kws.setdefault('events', ca.DBE_PROPERTY)
    kws.setdefault('format', 'CTRL')
    return getPV(pv, **kws)
