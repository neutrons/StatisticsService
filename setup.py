'''
Created on Mar 24, 2014

@author: xmr
'''

from distutils.core import setup

# Describe the package in some detail
long_desc = \
'''
The Mantid Statistics Server uses the Mantid package to listen to the SNS
ADARA data stream and output one or more EPICS process variables calculated
from data in the stream.

Exactly which process variables are calculated is specified in an external
configuration file. 
'''

setup(name='MantidStatisticsServer',
      version='0.1Alpha',
      description="A utility to generate EPICS PV's from the SNS ADARA stream",
      long_description= long_desc,
      author='Ross Miller',
      author_email='rgmiller@ornl.gov',
      url='https://github.com/neutrons/StatisticsService',
      requires = ['mantid (>= 3.1)'],
      # Note: I should also add a requirement for the pcaspy package, but it
      # doesn't appear to be installed via an RPM on the production servers,
      # so having it as a requirement would probably prevent this RPM from
      # actually installing.
      #py_modules = module_names,
      package_dir = {'': 'lib'},
      packages = ['mantidstats','mantidstats.plugins'],
      scripts = ['bin/mantidstats'],
      # data_files = [ ],
     )



# An example of how the 'data_files' keyword works.  We'll probably have an
# init.d script and a config file eventually.  They're not ready yet, though.
#data_files=[('bitmaps', ['bm/b1.gif', 'bm/b2.gif']),
#                  ('config', ['cfg/data.cfg']),
#                  ('/etc/init.d', ['init-script'])
