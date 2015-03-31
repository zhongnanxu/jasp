'''
Configuration dictionary for submitting jobs

mode = queue   # this defines whether jobs are immediately run or queued
user.name = jkitchin
user.email = jkitchin@andrew.cmu.edu

queue.command = qsub
queue.options = -joe
queue.walltime = 168:00:00
queue.nodes = 1
queue.ppn = 1
queue.mem = 2GB
queue.jobname = None

check for $HOME/.jasprc
then check for ./.jasprc
'''
import os

# default settings
JASPRC = {'vasp.executable.serial':'/opt/kitchingroup/vasp-5.2.12/build/bin/vasp-vtst',
 'vasp.executable.parallel':'/home-research/jkitchin/src/vasp/bin/vasp_openmpi_intel_mkl',
          'mode':'queue', #other value is 'run'
          'queue.command':'qsub',
          'queue.options':'-joe',
          'queue.walltime':'168:00:00',
          'queue.nodes':1,
          'queue.ppn':1,
          'queue.mem':'2GB',
          'queue.jobname':'None',
          'multiprocessing.cores_per_process':'None',
          'multiprocessing.cores_per_process': 'None',
          'vdw_kernel.bindat': '/opt/kitchingroup/vasp-5.3.5/vdw_kernel.bindat',
          'restart_unconverged': True
}

def read_configuration(fname):
    '''reads jasprc configuration from fname'''
    f = open(fname)
    for line in f:
        line=line.strip()

        if line.startswith('#'):
            pass # comment
        elif line == '':
            pass
        else:
            if '#' in line:
                # take the part before the first #
                line = line.split('#')[0]
            key,value = line.split('=')
            JASPRC[key.strip()] = value.strip()

# these are the possible paths to config files, in order of increasing
# priority
config_files = [os.path.join(os.environ['HOME'], '.jasprc'),
                '.jasprc']

for cf in config_files:
    if os.path.exists(cf):
        read_configuration(cf)
