#!/usr/bin/env python
'''
this is a patched Vasp calculator with the following features:

1. context manager to run in a specified directory and then return to the CWD.
2. calculations are run through the queue, not at the command line.
3. hook functions are enabled for pre and post processing
4. atoms is now a keyword
'''

import commands, exceptions, os, sys
from subprocess import Popen, PIPE
import numpy as np
from ase import Atoms
from ase.calculators.vasp import Vasp

def atoms_equal(self, other):
    '''
    check if two atoms objects are identical

    I monkeypatch the ase class because the ase.io read/write
    functions often result in float errors that make atoms not be
    equal. I use float tolerance for the comparison here.
    '''
    if other is None:
        return False

    TOLERANCE = 1e-6

    a = self.arrays
    b = other.arrays

    # check if number of atoms have changed.
    if len(self)!= len(other):
        return False

    if (a['numbers'] != b['numbers']).all():
        # atom types have changed
        return False

    if (np.abs(a['positions'] - b['positions']) > TOLERANCE).any():
        # something moved
        return False

    if (np.abs(self._cell - other.cell) > TOLERANCE).any():
        # cell has changed
        return False

    # we do not consider pbc becaue vasp is always periodic
    return True

Atoms.__eq__ = atoms_equal

#######################################################
# Vasp monkey patching this is done to ensure a job is submitted to
# the queue if it needs to be run.

# store original function so we can call it later
original_initialize = Vasp.initialize

def initialize(self, atoms):
    'initialize and write out the input files'
    original_initialize(self, atoms)
    from ase.io.vasp import write_vasp
    write_vasp('POSCAR', self.atoms_sorted, symbol_count = self.symbol_count)
    self.write_incar(atoms)
    self.write_potcar()
    self.write_kpoints()
    self.write_sort_file()

Vasp.initialize = initialize

class VaspQueued(exceptions.Exception):
    pass

class VaspSubmitted(exceptions.Exception):
    pass

class VaspRunning(exceptions.Exception):
    pass

class VaspNotFinished(exceptions.Exception):
    pass

''' pre_run and post_run hooks

the idea here is that you can register some functions that will run before and after running a Vasp calculation. These functions will have the following signature: function(self). you might use them like this

def set_nbands(self):
   do something if nbands is not set

calc.register_pre_run_hook(set_nbands)

def enter_calc_in_database(self):
   do something

calc.register_post_run_hook(enter_calc_in_database)

maybe plugins (http://www.luckydonkey.com/2008/01/02/python-style-plugins-made-easy/) are a better way?
'''
def register_pre_run_hook(function):
    if not hasattr(Vasp,'pre_run_hooks'):
        Vasp.pre_run_hooks = []
    Vasp.pre_run_hooks.append(function)

def register_post_run_hook(function):
    if not hasattr(Vasp,'post_run_hooks'):
        Vasp.post_run_hooks = []
    Vasp.post_run_hooks.append(function)

Vasp.register_pre_run_hook = staticmethod(register_pre_run_hook)
Vasp.register_post_run_hook = staticmethod(register_post_run_hook)

def run(self):
    '''monkey patch to submit job through the queue

    If this is called, then a job should be submitted or run.
    '''
    if hasattr(self,'pre_run_hooks'):
        for hook in self.pre_run_hooks:
            hook(self)

    if 'PBS_O_WORKDIR' in os.environ:
        # we are in the queue system, so we should just run vasp
        cmd = os.environ.get('VASP_SCRIPT',None)
        if cmd is None:
            raise Exception, '$VASP_SCRIPT not found.'
        exitcode = os.system(cmd)
        return exitcode

    # we are not in the queue, we determine if a job has been submitted

    JOBSTATUS = None
    # check if jobid file exists and if so, get jobid. if not,
    # calculation_required must have been true, so we will run a job
    if os.path.exists('jobid'):
        jobid = open('jobid').readline().strip()

        # see if jobid is in queue
        jobids_in_queue = commands.getoutput('qselect').split('\n')
        if jobid in jobids_in_queue:
            # get details on specific jobid
            status, output = commands.getstatusoutput('qstat %s' % jobid)
            if status == 0:
                lines = output.split('\n')
                fields = lines[2].split()
                job_status = fields[4]
                if job_status == 'C':
                    os.unlink('jobid')
                    #print 'job in queue but with status = C'
                    JOBSTATUS = 'Done'
                else:
                    os.chdir(self.cwd)
                    raise VaspQueued
            else:
                os.chdir(self.cwd)
                raise Exception, output
        else:
            JOBSTATUS = 'done'
            os.unlink('jobid')
    else:
        # no jobid, but maybe the calculation is done?
        # how do we tell if the job is done?
        if os.path.exists('vasprun.xml'):
            return None

    if JOBSTATUS is not None:
        if hasattr(self,'post_run_hooks'):
            for hook in self.post_run_hooks:
                hook(self)
        return None

    # if you get here, a job is getting submitted

    # we are not in the queue, so we need to submit this job
    p = Popen(['qsub',
               '-joe',
               '-N',
               "%s" % os.getcwd(),
               '-l walltime=168:00:00'],
              stdin=PIPE, stdout=PIPE, stderr=PIPE)

    # this is what python was called with
    # this only works when you call the python script from the cmd line
    # it does not work from emacs.
    scriptname = sys.argv[0]
    f = open(os.path.join(self.cwd,scriptname))
    lines = f.readlines()
    f.close()

    # make sure there is a header to run python and change to working directory
    header = ['#!/usr/bin/env python\n',
                 'import os\n'
                 '''os.chdir('{0}')\n'''.format(self.cwd)]

    footer = ['''os.unlink('jobid')\n''']
    script = ''.join(header + lines + footer)

    out, err = p.communicate(script)
    print out,err
    f = open('jobid','w')
    f.write(out)
    f.close()

    raise VaspSubmitted

Vasp.run = run

def pretty_print(self):
    '''
    __str__ function to print the calculator with a nice summary, e.g. vaspsum
    '''
    atoms = self.get_atoms()
    uc = atoms.get_cell()
    pos = atoms.get_positions()
    syms = atoms.get_chemical_symbols()

    if self.converged:
        energy = atoms.get_potential_energy()
        forces = atoms.get_forces()
    else:
        energy = np.nan
        forces = [np.array([np.nan, np.nan, np.nan]) for atom in atoms]

    if self.converged:
        stress = atoms.get_stress()
        if stress is None:
            stress = np.array([np.nan, np.nan, np.nan, np.nan, np.nan, np.nan])
        else:
            stress *= 0.1
    else:
        stress = np.array([np.nan, np.nan, np.nan, np.nan, np.nan, np.nan])

    # get a,b,c,alpha,beta, gamma
    from Scientific.Geometry import Vector
    A = Vector(uc[0,:])
    B = Vector(uc[1,:])
    C = Vector(uc[2,:])
    a = A.length()
    b = B.length()
    c = C.length()
    alpha = B.angle(C)*180/np.pi
    beta = A.angle(C)*180/np.pi
    gamma = B.angle(C)*180/np.pi
    volume = atoms.get_volume()

    s = []
    s.append(': -----------------------------')
    s.append('  VASP calculation from %s' % os.getcwd())
    s.append('  converged: %s' % self.converged)
    s.append('  Energy = %f eV' % energy)
    s.append('\n  Unit cell vectors (angstroms)')
    s.append('        x       y     z      length')
    s.append('  a0 [% 1.3f % 1.3f % 1.3f] %1.3f' % (uc[0][0],
                                                 uc[0][1],
                                                 uc[0][2],
                                                 A.length()))
    s.append('  a1 [% 1.3f % 1.3f % 1.3f] %1.3f' % (uc[1][0],
                                                 uc[1][1],
                                                 uc[1][2],
                                                 B.length()))
    s.append('  a2 [% 1.3f % 1.3f % 1.3f] %1.3f' % (uc[2][0],
                                                 uc[2][1],
                                                 uc[2][2],
                                                 C.length()))
    s.append('  a,b,c,alpha,beta,gamma (deg): %1.3f %1.3f %1.3f %1.1f %1.1f %1.1f' % (a,
                                                                              b,
                                                                              c,
                                                                              alpha,
                                                                              beta,gamma))
    s.append('  Stress (GPa):xx,   yy,    zz,    yz,    xz,    xy')
    s.append('            % 1.3f % 1.3f % 1.3f % 1.3f % 1.3f % 1.3f' % tuple(stress))
    s.append('  Volume = %1.2f A^3\n' % volume)

    s.append('  Atom,  sym, position (in x,y,z), rmsForce')
    for i,atom in enumerate(atoms):
        rms_f = np.sum(forces[i]**2)**0.5
        ts = '  %4i %4s [% 6.3f % 6.3f % 6.3f] % 1.2f' % (i,
                                                       atom.symbol,
                                                       atom.x,
                                                       atom.y,
                                                       atom.z,
                                                       rms_f)
        s.append(ts)


    s.append('--------------------------------------------------')
    if self.get_spin_polarized():
        s.append('Spin polarized: Magnetic moment = %1.2f' % self.get_magnetic_moment(atoms))

    # print all parameters that are set
    self.read_incar()
    for d in [self.int_params,
              self.float_params,
              self.exp_params,
              self.bool_params,
              self.list_params,
              self.dict_params,
              self.string_params,
              self.special_params]:

        for key in d:
            if d[key]:
                s.append('  %12s: %s' % (key, str(d[key])))

    return '\n'.join(s)

Vasp.__str__ = pretty_print

#########################################################################
def checkerr_vasp(self):
    ''' Checks vasp output in OUTCAR for errors. adapted from atat code'''
    error_strings = ['forrtl: severe',  #seg-fault
                     'highest band is occupied at some k-points!',
                     'rrrr', # I think this is from Warning spelled out in ascii art
                     'cnorm',
                     'failed',
                     'non-integer',]

    errors = []
    if os.path.exists('OUTCAR'):
        f = open('OUTCAR')
        for i,line in enumerate(f):
            i += 1
            for es in error_strings:
                if es in line:
                    errors.append(i,line)
        f.close()
        if len(errors) != 0:
            f = open('error', 'w')
            for i,line in errors:
                f.write('line {0}: {1}\n'.format(i,line))
            f.close()
    else:
        print os.getcwd()
        print os.listdir('.')
        raise Exception, 'no OUTCAR found'

def cleanvasp(self):
    'removes output files from directory'
    files_to_remove = ['CHG', 'CHGCAR', 'WAVECAR',
                       'EIGENVAL', 'IBZKPT', 'PCDAT', 'XDATCAR',
                       'vasprun.xml']
    for f in files_to_remove:
        if os.path.exists(f):
            os.unlink(f)

Vasp.register_post_run_hook(checkerr_vasp)

def Jasp(**kwargs):
    '''wrapper function to create a Vasp calculator

    **kwargs is the same as ase.calculators.vasp except that atoms can be used.

    you must be in the directory where vasp will be run.
    '''
    if 'atoms' in kwargs:
        atoms = kwargs['atoms']
        del kwargs['atoms']
        calc = Vasp(**kwargs)
        atoms.set_calculator(calc)
    elif len(kwargs) == 0:
        # eg Jasp(), returns calculator from what is in the directory
        calc = Vasp(restart=True)
    else:
        calc = Vasp(**kwargs)

    # finally, we return the calculator
    calc.cwd = os.getcwd()
    return calc

class jasp:
    '''Context manager for running Vasp calculations'''
    def __init__(self, dir, **kwargs):
        '''
        dir: the directory to run vasp in

        **kwargs: all the vasp keywords, including an atoms object
        '''

        self.cwd = os.getcwd()
        self.dir = dir
        self.kwargs = kwargs

    def __enter__(self):
        '''
        on enter, make sure directory exists, create it if necessary,
        and change into the directory. then return the calculator.
        '''
        #if __debug__:
        #    print('Entering {0}.'.format(self.dir)

        # make directory if it doesnt already exist
        if not os.path.isdir(self.dir):
            os.makedirs(self.dir)

        # now change to new working dir
        os.chdir(self.dir)

        calc = Jasp(**self.kwargs)
        calc.dir = self.dir
        calc.cwd = self.cwd
        return calc

    def __exit__(self,exc_type, exc_val, exc_tb):
        '''
        on exit, change back to the original directory.
        '''
        #if __debug__:
        #    print('Exiting {0}.'.format(self.dir)
        os.chdir(self.cwd)
        return False #allows exception to propogate out
