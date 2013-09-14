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
for N in ['STRING','CHAR','SHORT','LONG','ENUM','FLOAT','DOUBLE']:
    _name2type[N] = getattr(ca, 'DBR_'+N)

anychange = cothread.Event()

class CAValueBase(object):
    def __init__(self, pv):
        super(CAValueBase, self).__init__()
        self.__value = ca.ca_nothing(pv, ECA_DISCONN)

    @property
    def value(self):
        return self.__value

    def __getattr__(self, name):
        return getattr(self.__value, name)

    @property
    def val(self):
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

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.val

if MODE=='GET':
    class CAValue(CAValueBase):
        def __init__(self, pv, **kws):
            super(CAValue,self).__init__(pv)
            self.name=u'CAValue("%s",%s)'%(pv, kws)
            _L.debug('caget %s', repr(self))
            kws.pop('events',None)
            self.__value = ca.caget(pv, timeout=TIMO, throw=False, **kws)

elif MODE=='MONITOR':
    class CAValue(CAValueBase):
        def __init__(self, pv, **kws):
            super(CAValue,self).__init__(pv)
            self.name=u'CAValue("%s",%s)'%(pv, kws)
            _L.debug('camonitor %s', repr(self))
            self.__S = ca.camonitor(pv, self.__update, notify_disconnect=True,
                                    **kws)
            self.__last = ca.ca_nothing(pv, ECA_DISCONN)

        def __update(self, val):
            self.__last = val

            if not val.ok:
                _L.debug('monitor disconnect "%s"', repr(self))

            else:
                _L.debug('monitor update "%s"', repr(self))

            anychange.Signal()

else:
    raise ImportError("django setting CAJOP has invalid value '%s'"%MODE)

def getPV(pv, dtype=None, **kws):
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
        PV = CAValue(pv, **kws)
        _pv_cache[K] = PV
    return PV

# Fetch the value and render to a string
@register.simple_tag
def caget(pv, **kws):
    pv = pv.encode('ascii')
    val = getPV(pv, **kws)
    if val.ok and getattr(val, 'severity', 1)==0:
        return val.val
    else:
        return '%s: %s'%(val.sevr, val.val)

@register.simple_tag
def caspan(pv, default=u'No Conn', *args, **kws):
    pv = pv.encode('ascii')
    kws.setdefault('dtype', 'STRING') # let the server handle formatting
    val = getPV(pv, **kws)
    return ss.SafeUnicode(u'<span class="ca%s">%s</span>'%(val.sevr, val.val))

@register.assignment_tag
def caval(pv, **kws):
    pv = pv.encode('ascii')
    return getPV(pv, **kws)

@register.assignment_tag
def cameta(pv, **kws):
    pv = pv.encode('ascii')
    if DBE_PROP:
        kws.setdefault('events', ca.DBE_PROPERTY)
    kws.setdefault('format', 'CTRL')
    return getPV(pv, **kws)
