from distutils.core import setup

setup(name = 'jasp',
      version='0.9',
      description='extensions to ase.calculators.vasp',
      url='http://github.com/jkitchin/jasp',
      maintainer='John Kitchin',
      maintainer_email='jkitchin@andrew.cmu.edu',
      license='GPL',
      platforms=['linux'],
      packages=['jasp'],
      scripts=['jasp/bin/runjasp.py','jasp/bin/jaspsum'],
      long_description='''extensions to ase.calculators.vasp. jasp uses modern python patterns and tools.''',
      dependency_links = ['https://wiki.fysik.dtu.dk/ase-files/python-ase-3.7.1.3184.tar.gz#egg=ase'],
      
      install_requires=[
          'ase'
          #"svn+https://svn.fysik.dtu.dk/projects/ase/trunk", # ase
          #"numpy",
          #"matplotlib",
          #"scipy",
          #"webob",
          #"Django",
          #"pyxser",
          #"apsw"
          ],)
