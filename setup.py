'''
Created on Mar 24, 2014

@author: xmr
'''

from distutils.core import setup
import sys
import os
import os.path

# Install directories
PREFIX  = "/opt/mantidstats"
LIBDIR  = "%s/lib"%PREFIX
BINDIR  = "%s/bin"%PREFIX
CONFDIR = "%s/etc"%PREFIX
INITDIR = "/etc/init.d"

INIT_SCRIPT_NAME='mantidstats'

# I want to specify some non-standard install directories and the easiest
# way to do that is with a setup.cfg file.  Unfortunately, the values in
# that file are not available to this script.  So, this function creates a
# temporary setup.cfg file, puts the values I want in it, and closes the file.
#
# Yes, I know this is an abuse of how the setup.cfg file should be used.
def create_temp_cfg_file():
    f=open("setup.cfg", "w")
    f.write("[install]\n")
    f.write("prefix=%s\n"%PREFIX)
    f.write("install_lib=%s\n"%LIBDIR)
    #f.write("#install_scripts=some/bin/path\n"
    #f.write("#install-base = /opt/mantidstats\n")
    f.close()

def remove_temp_cfg_file():
    os.remove( 'setup.cfg')


# Make sure the init.d script has the proper directories in it, too
def generate_init_script():
    infile = open('mantidstats.initd.template', 'r')
    outfile = open(INIT_SCRIPT_NAME, 'w')
    for l in infile.readlines():
        # Look for strings to replace
        n = l.find('__REPLACE_ME_EXEC__')
        if n != -1:
            outfile.write(l[0:n])
            outfile.write("%s/mantidstats\n"%BINDIR)
            continue
        
        n = l.find('__REPLACE_ME_CONFIGFILE__')
        if n != -1:
            outfile.write(l[0:n])
            outfile.write("%s/mantidstats.conf\n"%CONFDIR)
            continue
        
        outfile.write(l)
        
    infile.close()
    outfile.close()
    os.chmod( INIT_SCRIPT_NAME, 0755) # make the init.d script executable

# Remove the updated init script once we're done with it
def remove_init_script():
    os.remove( INIT_SCRIPT_NAME)




# -----------------------------------------------------------
# The main part of the setup program
# -----------------------------------------------------------

# Describe the package in some detail
long_desc = \
'''
The Mantid Statistics Server uses the Mantid package to listen to the SNS
ADARA data stream and output one or more EPICS process variables calculated
from data in the stream.

Exactly which process variables are calculated is specified in an external
configuration file. 
'''

# various non-python files
data_files = [ (CONFDIR, ['mantidstats.conf']),
               (INITDIR, [INIT_SCRIPT_NAME]),
             ]

# In the process of building the rpm package, this setup.py file actually gets
# executed twice.  We only want to mess with the cfg and init.d files on the
# first pass.
if sys.argv[1] == 'bdist_rpm':
    # Generate an init.d script with the proper directory names in it
    generate_init_script()

    # If a setup.cfg file exists, don't overwrite it.
    # (We'll just have to hope that whoever put the file there
    # knew what he/she was doing.)
    delete_setup_cfg = False
    print "----------", os.getcwd()
    if not os.path.isfile( 'setup.cfg'):
        delete_setup_cfg = True
        create_temp_cfg_file()

setup(name='MantidStatisticsServer',
      version='0.7Beta',
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
      data_files = data_files,
     )

if sys.argv[1] == 'bdist_rpm':
    if delete_setup_cfg:
        remove_temp_cfg_file()

    remove_init_script()

