#!/usr/bin/env python2
# -*- coding: utf-8 -*-
'''
This file is part of tumorcode project.
(http://www.uni-saarland.de/fak7/rieger/homepage/research/tumor/tumor.html)

Copyright (C) 2016  Michael Welter and Thierry Fredrich

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

if __name__ == '__main__':
  import os.path, sys
  sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)),'../..'))
import os, sys
from os.path import  basename, dirname
  
import identifycluster
if identifycluster.name == 'snowden':
  import matplotlib
  matplotlib.use('Agg') 
import qsub
import dicttoinfo
import myutils
import h5py
import h5files
import itertools
import time
import string
import numpy as np

#sys.path.append(join(dirname(__file__),'/localdisk/thierry/tc_install/py/krebs/adaptionAnalysis'))
#from krebs.adaption import getVesselTypes
from third_party.pso import *


#import krebs.adaption

from krebsjobs.parameters import parameterSetsAdaption
import krebsjobs.submitAdaption
#import krebsjobs.parameters.tumorParameters as parameterSets_tum

import krebsutils
if sys.flags.debug: # library search path made known by initialization of krebsutils
  adaption_cpp = __import__('libadaption_d', globals(), locals())
else:
  adaption_cpp = __import__('libadaption_', globals(), locals())

#globals
calculated_mean_cap_flow = 0.0

# velocity in capillary about 1mm/s = 1000mu/s
# typical diameter 5mu e.g r=2.5mu
# 3.1415*2.5*2.5*1000 about 2e4
suggested_cap_flow = 20000.;

def con(x, *args):
  #global calculated_mean_cap_flow
  return np.square(calculated_mean_cap_flow-10e4)
def con2(x, *args):
  #global calculated_mean_cap_flow
  return np.square(calculated_mean_cap_flow-10e5)
def con3(x, *args):
  #global calculated_mean_cap_flow
  return np.square(calculated_mean_cap_flow-10e6)
def con4(x, *args):
  # velocity in capillary about 1mm/s = 1000mu/s
  # typical diameter 5mu e.g r=2.5mu
  # 3.1415*2.5*2.5*1000 about 2e4
  return np.square(calculated_mean_cap_flow-20000)
def do_pSO_for_file(x,dst_file, vesselgroup, parameters):
  parameters['counter'] = parameters['counter'] + 1
  alabel = 'data_%i' % parameters['counter']
  
  #hack
  parameters['adaption']['avgRootNodeConductivity'] = 0.0
  
  #pso stuff
  #write current parametr variation to parametres object
  #so this goes to h5 file and goes to the adaption
  parameters['adaption']['k_m'] = x[0]
  parameters['adaption']['k_c'] = x[1]
  parameters['adaption']['k_s'] = x[2]
  #parameters['adaption']['cond_length'] = x[3]
  #parameters['adaption']['Q_refdot'] = x[4]
  # running adaption
  print('creating dataset: %s' % alabel)
  gdst = dst_file.create_group(alabel)
  
  if parameters['counter']%50>0:
    parameters['adaption']['write2File'] = False
  else:
    parameters['adaption']['write2File'] = True
    myutils.hdf_write_dict_hierarchy(gdst, 'parameters', parameters)
  #print('We run: vesselgroup: %s, parameters[\'adaption\']: %s, parameters[\'calcflow\'] %s, gdst %s\n' % (vesselgroup, parameters['adaption'], parameters['calcflow'], gdst))
  
  return_state, mean_flow_cap,std_flow_cap = adaption_cpp.computeAdaption(vesselgroup, parameters['adaption'], parameters['calcflow'], gdst)
  
  # creating opt criterion
  if return_state == 0:
    #it was convergent
#    veins, arteries, capillaries = getVesselTypes(gdst['vessels_after_adaption'])
#    edges, flows = krebsutils.read_vessels_from_hdf(gdst['vessels_after_adaption'],['flow'])
#    this_std = np.std(flows[capillaries])
#    #gdst.file.flush()
#    del gdst['recomputed']
#    del gdst['vessels_after_adaption']
    print('Adaption convergent!')
    print('mean(flow): %f, std(flow): %f ' % (mean_flow_cap,std_flow_cap))
    global calculated_mean_cap_flow
    calculated_mean_cap_flow = mean_flow_cap
    deviation_from_suggested_cap_flow = np.square(mean_flow_cap-suggested_cap_flow)
    return deviation_from_suggested_cap_flow
  else:
    print('Adaption crashed!') #we dont like that, big penalty
    return sys.float_info.max
       

def worker_on_client(fn, grp_pattern, adaptionParams, num_threads):
  print('Adaption on %s / %s / param: %s' % (fn, grp_pattern, adaptionParams['name']))
  h5files.search_paths = [dirname(fn)] # so the plotting and measurement scripts can find the original tumor files using the stored basename alone
  krebsutils.set_num_threads(num_threads)
  
  vesselgroup = h5files.open(fn, 'r', search = False)[grp_pattern]
  f_opt_data = h5files.open('PSO_data_%s_%s.h5' % (basename(fn),adaptionParams['name']), 'a', search = False)
  
  adaptionParams['counter'] = 0
  #for default_pso use only 20, hope this speed up
  #for all other simulations 50 was used here
  adaptionParams['adaption']['max_nun_iterations'] = 100
  #large_3d_H2 had no convergence after a
  #night. So I try more iterations per run
  #adaptionParams['adaption']['max_nun_iterations'] = 500
  adaptionParams['adaption']['Q_refdot'] = 40
  adaptionParams['adaption']['S_0'] = 20
  # initialize parameters
  #x_0= [1.5, 1.5, 1]
  lb= [0.5, 0.5, 0.5]
  ub= [4, 4, 4]
#  x_0= [1.5, 1.5, 1, 2500.,40]
#  lb= [0.5, 0.5, 0.5, 500,10]
#  ub= [4, 4, 4, 3500,80]
  #x_0[0] =adaptionParams['adaption']['k_m']
  #x_0[1] =adaptionParams['adaption']['k_c']
  #x_0[2] =adaptionParams['adaption']['k_s']
  #x_0[3] =adaptionParams['adaption']['cond_length']
  #x_0[4] =adaptionParams['adaption']['Q_refdot']
  
  if 0:#hope_final
    swarmsize = 50
    maxiter = 10
    minstep = 1e-8  #default 1e-8
    minfunc = 0.001  #default 1e-8
    omega = 0.5     #default 0.5
  if 0:#hope_final_phase
    adaptionParams['calcflow']['includePhaseSeparationEffect'] = True
    swarmsize = 50
    maxiter = 10
    minstep = 1e-8  #default 1e-8
    minfunc = 0.001  #default 1e-8
    omega = 0.5     #default 0.5
  if 0:#big_swarm
    swarmsize = 100
    maxiter = 20
    minstep = 1e-8  #default 1e-8
    minfunc = 0.001  #default 1e-8
    omega = 0.5     #default 0.5
    adaptionParams['starting_radii'] = 10.,
  if 0:#big_swarm2
    swarmsize = 500
    maxiter = 20
    minstep = 1e-8  #default 1e-8
    minfunc = 0.001  #default 1e-8
    omega = 0.5     #default 0.5
  '''
  omega : scalar
      Particle velocity scaling factor (Default: 0.5)
  phip : scalar
      Scaling factor to search away from the particle's best known position
      (Default: 0.5)
  phig : scalar
      Scaling factor to search away from the swarm's best known position
      (Default: 0.5)
  '''
  if 1:#medium for small configs
    swarmsize = 500
    maxiter = 5
    minstep = 1e-8  #default 1e-8
    minfunc = 0.001  #default 1e-8
    omega = 0.5     #default 0.5
  if 0:#big_swarm3
    swarmsize = 1000
    maxiter = 20
    minstep = 1e-8  #default 1e-8
    minfunc = 0.001  #default 1e-8
    omega = 0.5     #default 0.5
  if 0:#big_swarm3_phase
    swarmsize = 1000
    maxiter = 20
    minstep = 1e-8  #default 1e-8
    minfunc = 0.001  #default 1e-8
    omega = 0.5     #default 0.5
    adaptionParams['calcflow']['includePhaseSeparationEffect'] = True
  if 0:#big_swarm_phase
    adaptionParams['calcflow']['includePhaseSeparationEffect'] = True
    swarmsize = 100
    maxiter = 20
    minstep = 1e-8  #default 1e-8
    minfunc = 0.001  #default 1e-8
    omega = 0.5     #default 0.5
    adaptionParams['starting_radii'] = 10.,
  if 0:#bigbig
    adaptionParams['calcflow']['includePhaseSeparationEffect'] = True
    swarmsize = 250
    maxiter = 30
    minstep = 1e-8  #default 1e-8
    minfunc = 0.001  #default 1e-8
    omega = 0.5     #default 0.5
  
#  swarmParams1 = dict()
#  swarmParams1['name'] = 'compare_phase_big'
#  swarmParams1['swarmsize'] = 100
#  swarmParams1['maxiter'] = 100
#  swarmParams1['minstep'] = 1e-8  #default 1e-8
#  swarmParams1['minfunc'] = 0.001 #default 1e-8
#  swarmParams1['omega'] = 0.5     #default 0.
#  maxiter = 20
  processes = 1 #somehow only 1 supported, pickels problem
  adaptionParams['num_threads'] = 4
  
  args=(f_opt_data, vesselgroup, adaptionParams)
  if 0:
    xopt, fopt = pso(do_pSO_for_file,
                     x_0,
                     lb,
                     ub,
                     ieqcons=[con4],
                     debug=True,
                     swarmsize= swarmsize,
                     maxiter= maxiter,
                     minstep=minstep,
                     minfunc=minfunc,
                     omega=omega,
                     processes=processes,
                     use_initial_guess=use_initial_guess,
                     phig=0.25,
                     args=args)
  if 1:
    xopt, fopt = pso(do_pSO_for_file,
                     lb,
                     ub,
                     debug=True,
                     swarmsize= swarmsize,
                     maxiter= maxiter,
                     minstep=minstep,
                     minfunc=minfunc,
                     omega=omega,
                     processes=processes,
                     args=args)                   
  
  f_opt_data.attrs.create('xopt', data = xopt)
  f_opt_data.attrs.create('fopt', data = fopt)
  

  h5files.closeall() # just to be sure
  

def run2(parameter_set, filenames, grp_pattern):
  print 'submitting ...', parameter_set['name']
 

  num_threads = 1
  if 'num_threads' in parameter_set:
    num_threads = parameter_set['num_threads']
    
  for fn in filenames:
    qsub.submit(qsub.func(worker_on_client, fn, grp_pattern, parameter_set, num_threads),
                  name = 'job_adaption_'+parameter_set['name']+'_'+basename(fn),
                  num_cpus = num_threads,
                  days = 4.,
                  mem = '3500MB',
                  change_cwd = True)

def run_reproduze(filenames):
  for fn in filenames:
    root_grp = h5files.open(fn, 'r', search = False)['/']
    param_grp = h5files.open(fn, 'r', search = False)['/data_50/parameters']
    parameter_name_set = param_grp['name'].value
    try:
      if not parameter_name_set in dir(parameterSetsAdaption):
        raise AssertionError('Unknown parameter set %s!' % parameter_name_set)
      if not 'xopt' in root_grp.attrs.keys():
        raise AssertionError('Are you sure %s is successfully optimized?' % fn)
      else:
        xopt = np.asarray(root_grp.attrs.get('xopt'))
    except Exception, e:
        print e.message
        sys.exit(-1)
    factory = getattr(parameterSetsAdaption, parameter_name_set)
    factory['name'] = parameter_name_set
    factory['adaption'].update(
      k_m = xopt[0],
      k_c = xopt[1],
      k_s = xopt[2],
      cond_length = xopt[3],
      max_nun_iterations = 200,
    )
    num_threads = 1
    if 'num_threads' in factory:
      num_threads = factory['num_threads']
    qsub.submit(qsub.func(krebsjobs.submitAdaption.worker_on_client, fn, '/data_50/recomputed', factory, num_threads),
                  name = 'job_adaption_'+factory['name']+'_'+basename(fn),
                  num_cpus = num_threads,
                  days = 4.,
                  mem = '3500MB',
                  change_cwd = True)

if not qsub.is_client and __name__=='__main__':
  import argparse
  parser = argparse.ArgumentParser(description='particle swarm optimization for all files in file in filenames')  
  #parser.add_argument('AdaptionParamSet')  
  #parser.add_argument('fileNames', nargs='?', type=argparse.FileType('r'), default=sys.stdin, help='Vessel file to calculate')  
  subparsers = parser.add_subparsers(dest='subcommand')
  parser_run = subparsers.add_parser('run')
  #parser_run.add_argument('fileNames', nargs='+', type=argparse.FileType('r'), default=sys.stdin, help='Vessel file to calculate')
  parser_run.add_argument('-f','--fileNames', nargs='*',  help='Vessel file to calculate')
  parser_run.add_argument('-p','--AdaptionParamSet')  
  parser_run.add_argument('-g','--grp_pattern',help='Where to find the vessel group in the file')  
  #parser.add_argument('-a', '--analyze', help = 'loop through all files analyze data and make plot', default=False, action='store_true')
  parser_rep =  subparsers.add_parser('rep')   
  parser_rep.add_argument('-f', '--fileNames', nargs='*',  help='Vessel file to calculate')
  #parser.add_argument('-r', '--reproduze', help = 'reproduced vesselnetwork with optimized parameters', default = False, action='store_true')  
  
  goodArguments, otherArguments = parser.parse_known_args()
  
  
  
  
  if goodArguments.subcommand == 'rep':
    goodArguments_rep, otherArguments_rep = parser_rep.parse_known_args()
    qsub.parse_args(otherArguments_rep)
    filenames = goodArguments_rep.fileNames
#    #create filename due to former standards
#    filenames=[]
#    for fn in goodArguments_run.fileNames:
#      filenames.append(fn.name)
    run_reproduze(filenames)
  if goodArguments.subcommand == 'run':
    goodArguments_run, otherArguments_run = parser_run.parse_known_args()
    qsub.parse_args(otherArguments)
    filenames = goodArguments_run.fileNames
#    #create filename due to former standards
#    filenames=[]
#    for fn in goodArguments_run.fileNames:
#      filenames.append(fn.name)
    try:
      if not goodArguments_run.AdaptionParamSet in dir(parameterSetsAdaption):
        raise AssertionError('Unknown parameter set %s!' % goodArguments_run.AdaptionParamSet)
    except Exception, e:
        print e.message
        sys.exit(-1)
        
    factory = getattr(parameterSetsAdaption, goodArguments_run.AdaptionParamSet)
    #single parameter set chosen  
    if factory.__class__ == dict:
      factory['name'] = goodArguments_run.AdaptionParamSet
      run2(factory, filenames, goodArguments_run.grp_pattern)
    #a list of paramset e.g. for different boundary parameters.
    if factory.__class__==list:
      for paramset in factory:
        run2(paramset, filenames, goodArguments_run.grp_pattern)    
      
