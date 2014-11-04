#!/usr/bin/env python

import logging
_log=logging.getLogger('cagraph')

import re, json

import matplotlib
matplotlib.use("Agg")

from matplotlib import pyplot
import matplotlib.dates as mdates

from carchive.untwisted import arget, RAW, PLOTBIN, EXACT

import cothread

pvpat=re.compile(r'pv(\d+)')

def getargs():
  from optparse import OptionParser
  P = OptionParser()
  P.add_option("-v", "--verbose", action='store_const', const=logging.DEBUG, default=logging.INFO,
               help='Print much more information')
  return P.parse_args()

class plot_history(object):
  def __init__(self, conf):
    assert 'file' in conf, 'no file name in %s'%conf
    self.conf = conf

  def plot(self):
    fig = pyplot.figure()
    # bounding box [left, bottom, width, height]
    ax0 = ax = fig.add_axes(self.conf.get('shape', [0.1, 0.1, 0.8, 0.8]))
    ax.hold(True)

    axone=False
    for tr in self.conf['traces']:
      if 'pv' in tr:
        val, meta = arget(tr['pv'], match=EXACT, mode=PLOTBIN, count=tr.get('count',200),
                          start=self.conf['start'], end=self.conf.get('end'),
                          archs=tr.get('archives'))

        val = val[:,0]
        T = mdates.epoch2num(meta['sec']+1e-9*meta['ns'])
        # style
        # color: bgrcmykw
        # line: - -- -. :
        # marker: .,o*x
        L = ax.plot(T, val, tr.get('style','-'), **tr.get('attrs', {"label":tr['pv']}))

        if 'fill' in tr:
          ax.fill_between(T, val, color=tr['fill'])

      elif 'yaxis' in tr:
        if axone:
          ax = ax.twinx()
        axone = True
        ax.set_ylabel(tr['yaxis'])
        ax.set_yscale(tr.get('scale','linear'))
        if 'min' in tr:
          #ax.autoscale(axis='y', enable=False)
          ax.set_ylim(tr['min'], tr['max'])

    if 'legend' in self.conf:
      handles, labels = [], []
      for ax in fig.get_axes():
        H, L = ax.get_legend_handles_labels()
        handles.extend(H)
        labels.extend(L)
      # for legend location codes
      # http://matplotlib.org/api/figure_api.html#matplotlib.figure.Figure.legend
      fig.legend(handles, labels, self.conf['legend'])

    majloc = mdates.AutoDateLocator()
    majfmt = mdates.AutoDateFormatter(majloc)

    ax0.xaxis.set_major_locator(majloc)
    ax0.xaxis.set_major_formatter(majfmt)

    ax0.xaxis.grid(True)
    ax0.yaxis.grid(True)

    if 'title' in self.conf:
      fig.suptitle(self.conf['title'])

    fig.autofmt_xdate()

    # MPL docs claim this is done by autofmt_xdate(), but it isn't w/ 1.1.1~rc2-1
    for lbl in ax0.get_xticklabels():
      lbl.set_rotation(20)

    fig.savefig(self.conf['file'])
    _log.info('wrote %s', self.conf['file'])

plottypes={
  'plot_history':plot_history,
}

def ewrap(fn, conf):
  try:
    period = float(conf.get('period', '60'))
    F = fn(conf)
    while True:
      F.plot()
      cothread.Sleep(period)
  except:
    _log.exception('unhandled exception in %s', conf)

def main():
  opts, files = getargs()

  logging.basicConfig(level=opts.verbose)

  for F in files:
    _log.info('read %s', F)
    with open(F, 'r') as fp:
      conf = json.load(fp)

    for S in conf:
      if 'type' not in S:
        continue

      type = S['type']
      fn = plottypes.get('plot_'+type)
      if fn is None:
        raise ValueError('unknown graph type %s'%type)
      
      cothread.Spawn(ewrap, fn, S)

  _log.info('Running')
  cothread.WaitForQuit()

if __name__=='__main__':
  main()
