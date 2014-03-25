'''
Created on Jan 30, 2014

@author: xmr
'''


'''
TODO List:
- Figure out how best to store individual PV calc callables (or classes) - probably separate .py files in a package?
- Document the keyword params that will be passed to the callables
- There is a perceptible amount of time between the ChunkProcessing and PostProcessing algorithms.  Specifically, it
  was not uncommon for the EVTCNT and EVTCNT_POST to differ when polled with caget.  Need to discuss this with some
  of the instrument scientists and determine if that could cause problems.
- Figure out how to daemonize python programs.  I think there's a package for that...
- There a lot more to the pcaspy library to figure out. I think I'm using it properly, but I have no idea about
  any other useful features that might exist. 
- Figure out a way to specify the mantid library location in the config file (the sys.path.append() and import
  statements are normally executed well before the config file is parsed...)
- If we don't have any PV's that require the post-processing step, then don't set the 'PreserveEvents' and
  'PostProcessingAlgorithm' parameters in StartLiveListener()  (saves memory and CPU cycles down in Mantid)
- Add code to handle improper regex strings in plugin definitions
- Define one or more exceptions for the calculation functions to throw when
  they encounter errors.  Have the ChunkProcessing and PostProcessing
  algorithms trap the exceptions and set the appropriate EPICS error flags for
  the PV 
- Need a setup.py script so I can build RPM's (include an init.d script)
- Need to remove the hard-coded path extension for importing pcaspy

Config related tasks:
- Figure out global config options ( update rate for live listener, preserve events, locations for plugin dirs?)
- Figure out beamline config options (beamline name, beamline prefix, which PV's to calculate)
- Make the code robust enough to handle improperly written config files (at least fail gracefully)
- Allow users to specify the update rate (ie: the value of the 'scan' field in pvdb) for each PV

'''

import sys
import os
import re  # regex processing for the PV calculation callables

from optparse import OptionParser
import ConfigParser

import logging
import logging.handlers

# Try to figure out where Mantid is installed and set sys.path accordingly
if os.environ.has_key('MANTIDPATH'):
    #MANTIDPATH env var should be set by the Mantid installer.
    sys.path.append( os.environ['MANTIDPATH'])

# If the env var wasn't set, we'll just hope for the best.  It's possible
# the PYTHONPATH variable has already been modified to include the 
# Mantid libraries...
try:
    from mantid.simpleapi import *
    from mantid.api import IEventWorkspace
#    from mantid.api import Run
    from mantid.api import PythonAlgorithm, AlgorithmFactory, WorkspaceProperty
    from mantid.kernel import Direction
except ImportError, e:
    print """
Failed to import the Mantid framework libraries.
Please make sure that Mantid has been installed properly and that either the
MANTIDPATH or PYTHONPATH environment variables include the directory where
Mantid has been installed.
"""
    print "Aborting."
    sys.exit(1)


# pcaspy library for EPICS stuff
# Again, using a hard-coded path
sys.path.append('/opt/pcaspy/lib64/python2.7/site-packages/pcaspy-0.4.1-py2.7-linux-x86_64.egg')
from pcaspy import SimpleServer, Driver

# Not quite ready for the daemon stuff yet...
## Try to use the daemon package.  But continue anyway if it's not available
#NO_DAEMON_PKG=False
#try:
#    import daemon
#except ImportError:
#    NO_DAEMON_PKG=True

# Need a few dictionaries here:  two to map PV names to the functions
# that calculate their values and another to map PV names to their current
# values.  Also need a list to hold the PV names the user wants us to 
# calculate.
# 
# TODO: Find a way avoid having to use global variables here.  The problem
# is that they are used by the Algorithm instances, and those classes are
# instantiated down in the Mantid code so I can't pass anything to their
# constructors...
PV_Functions_Chunk = {}
PV_Functions_Post = {}
PV_Values = {}
PROCESS_VARIABLES = []

# Another global: The name of the logger object.  Using a global so that all
# the different functions can log to the same location. (And also the two
# Algorithm objects can also use it.)
# The 'pythonic' way is to use the name of the module, but in this case 
# 'main' is a lousy name for a logger.
LOGGER_NAME="MantidStats"


def build_pvdb():
    '''
    Generates the pvdb dictionary to pass to createPV()
    '''
    pvdb = { }
    
    for name in PROCESS_VARIABLES:
        pvdb[name] = { 'prec' : 5, 'scan' : 1}
        # for now, all variables will have a precision of 5
        # There's a lot of other fields we could add, so we might want to make
        # this more customizable.
        #
        # The scan field should probably match the UpdateEvery parameter to
        # StartLiveData.  (There's no point having the PV update any faster
        # than the live listener runs.) 
    
    return pvdb

class myDriver(Driver):
    
    def __init__(self):
        super(myDriver, self).__init__()
        
        # initialize a holder for the event counts (so we have something to
        # return if we hit an exception trying to update.  See read() below.)
        self._EventCounts = 0
        
    def read(self, reason):
        # This is pretty simple - just fetch the correct value from PV_Values
        try:
            value = PV_Values[reason]   # reason is the name of the PV (without
                                        # the prefix)
        except KeyError:
            # Value hasn't been calculated (yet?)
            value = None
            #value = self.getParam(reason)
                   
        return value  
    
class ChunkProcessing(PythonAlgorithm):
    def PyInit(self):
        # Declare properties
        self.declareProperty(WorkspaceProperty("InputWorkspace", "", direction=Direction.Input))
        self.declareProperty(WorkspaceProperty("OutputWorkspace", "", direction=Direction.Output))
        
    def PyExec(self):
        # Run the algorithm
        logger = logging.getLogger(LOGGER_NAME)
        logger.debug( "Running the ChunkProcessing algorithm")
    
        # TODO: What other parameters might PV functions want to know?
    
        # Call each PV's calculation function    
        inputWS = self.getProperty("InputWorkspace").value
        if not isinstance(inputWS, IEventWorkspace):
            logger.error( "InputWorkspace was a type '%s' instead of an IEventWorkspace"%type(inputWS).__name__)
            logger.error( "Attempting to continue, but this is likely to cause Mantid to crash eventually.")
                        
        for PV in PROCESS_VARIABLES:
            if PV in PV_Functions_Chunk:
                # Note: Always use keyword args when calling the PV functions.
                # Positional arguments are not allowed because we didn't want
                # to force a particular function signature on everyone.
                # Instead, we document what keywords are passed and what they
                # mean; authors of PV functions can pick and choose which
                # keywords are important to their particular function.
                PV_Values[PV] = PV_Functions_Chunk[PV]( chunkWS = inputWS,
                                                        accumWS = None,
                                                        pv_name = PV,
                                                        run_num = inputWS.getRunNumber(),
                                                        logger_name = LOGGER_NAME
                                                      )
                # Note: If you change the list of keyword parameters, be sure
                # to update README.md!!!
            #else:
                #logger.error( "No function for calculating value of %s"%PV)
            
        # Since we don't modify the data in any way, we don't need to copy
        # the input over to the output workspace.
            
AlgorithmFactory.subscribe( ChunkProcessing())

        
class PostProcessing(PythonAlgorithm):
    def PyInit(self):
        # Declare properties
        self.declareProperty(WorkspaceProperty("InputWorkspace", "", direction=Direction.Input))
        self.declareProperty(WorkspaceProperty("OutputWorkspace", "", direction=Direction.Output))
        
    def PyExec(self):
        # Run the algorithm
        logger = logging.getLogger(LOGGER_NAME)
        logger.debug( "Running the PostProcessing algorithm")
        
        # Call each PV's calculation function
        inputWS = self.getProperty("InputWorkspace").value
        if not isinstance(inputWS, IEventWorkspace):
            logger.error( "InputWorkspace was a type '%s' instead of an IEventWorkspace"%type(inputWS).__name__)
            logger.error( "Attempting to continue, but this is likely to cause Mantid to crash eventually.")
            # Note:  The workspace *WON'T* be an IEventWorkspace unless the 'PreserveEvents' option
            # is used when calling StartLiveData.  For now, it's hard-coded to True, but we might
            # want to make that optional if we start running out of memory because the workspaces
            # are getting too big.
                        
        for PV in PROCESS_VARIABLES:
            if PV in PV_Functions_Post:
                # Note: Always use keyword args when calling the PV functions.
                # Positional arguments are not allowed because we didn't want
                # to force a particular function signature on everyone.
                # Instead, we document what keywords are passed and what they
                # mean; authors of PV functions can pick and choose which
                # keywords are important to their particular function.
                PV_Values[PV] = PV_Functions_Post[PV]( chunkWS = None,
                                                       accumWS = inputWS,
                                                       pv_name = PV,
                                                       run_num = inputWS.getRunNumber(),
                                                       logger_name = LOGGER_NAME
                                                     )
                # Note: If you change the list of keyword parameters, be sure
                # to update README.md!!!
            #else:
                #logger.error( "No function for calculating value of %s"%PV)
        
        # Last step - copy the input over to the output
        #outputWS = mtd[ self.getPropertyValue("OutputWorkspace")]
        #outputWS = inputWS
        # In theory, we shouldn't have to copy the input to the output if we
        # don't modify the data, but for some reason, we do.  Also, the
        # outputWS = inputWS line should suffice, but again for some reason
        # it doesn't.  Russell is looking in to both these problems.  In the
        # meantime, clone() works find.
        inputWS.clone(OutputWorkspace = self.getPropertyValue("OutputWorkspace"))
        
AlgorithmFactory.subscribe( PostProcessing())  



def import_plugins( plugin_dirs, chunk_regex, post_regex):
    '''
    Import plugins for calculating PV's
    
    Iterates through the list of directories where plugins might be found (the
    plugin_dirs parameter).  For each dir, it iterates through the list of
    files.  For each .py file, it reads the file and tries to call the
    function 'register_pvs'.
    '''
    
    logger = logging.getLogger(LOGGER_NAME)
    
    for d in plugin_dirs:
        sys.path.append(d)
        try:
            for f in os.listdir(d):
                if os.path.isfile(os.path.join(d,f)):
                    if f[-3:] == '.py':
                        # OK, found a python file.  Import register_pvs
                        m = __import__(f[:-3])
                        try:
                            (chunk, post) = m.register_pvs()
                            
                            # compile the regex strings returned by
                            # register_pvs() into compiled re objects
                            # TODO: Properly handle poorly defined regex strings!
                            for k in chunk:
                                chunk_regex[re.compile(k)] = chunk[k]
                            
                            for k in post:
                                post_regex[re.compile(k)] = post[k]

                        except AttributeError:
                            logger.warning( "Module '%s' in directory '%s' has no 'register_pvs' function.  Ignoring this module" %(f, d))
        except OSError:
            logger.warning( "Plugin directory '%s' does not exist.  Continuing plugin processing." % d)
        
        # Done loading plugins from the directory, so remove it from sys.path
        sys.path = sys.path[:-1]
        

def main():
    '''
    Parse the command line options and config file, then start up the mantid
    live listener and begin exporting the requested process variables.
    '''
    
    # First, parse the command line options
    parser = OptionParser()
    parser.add_option("-f", "--config_file", dest="config",
                      help="the name of the configuration file",
                      metavar="CONFIG_FILE",
                      default='mantidstats.conf')
    parser.add_option("-d", "--plugin_dir", dest="plugin_dirs", 
                      action="append", type="string",
                      metavar="PLUGIN_DIR",
                      help="a directory where plugin files are located  (option may be specified multiple times)")
    parser.add_option("", "--console_log",
                      help="Log to std err.  (Default is to use syslog)",
                      action="store_true")
    parser.add_option("", "--debug",
                      help="Include debugging messages in the log",
                      action="store_true")

    parser.set_defaults(config="mantidstats.conf")  
    (options, args) = parser.parse_args()
    
            
    # Set up logging
    root_logger = logging.getLogger()
    if options.console_log:
        console_handler = logging.StreamHandler()
        # Add a timestamp to logs sent to std err (syslog automatically adds
        # its own timestamp, so we don't need to include ours in that case)
        formatter = logging.Formatter('%(asctime)s - %(name)s: - %(levelname)s - %(message)s')
        console_handler.setFormatter( formatter)
        root_logger.addHandler( console_handler)
    else:
        syslog_handler = logging.handlers.SysLogHandler('/dev/log')
        
        # Re-map the syslog handler's priority for the DEBUG level because
        # 'debug' level messages are probably filtered out by the syslog
        # daemon itself.
        syslog_handler.priority_map['DEBUG'] = 'info'

        formatter = logging.Formatter('%(name)s: - %(levelname)s - %(message)s')
        syslog_handler.setFormatter( formatter)
        root_logger.addHandler( syslog_handler)
        
    if options.debug:
        root_logger.setLevel( logging.DEBUG)
    else:
        root_logger.setLevel( logging.INFO)

    logger = logging.getLogger( LOGGER_NAME)
    logger.info( "Starting Mantid Statistics Service...")
    logger.debug( "Debug log level is set.")
    
    # I'd prefer to have this up by the call to parse_args(), but we
    # haven't set up a logger at that point...
    # Log a warning if there are any extra command line arguments
    if len(args):
        logger.warning( "Extraneous command line arguments: %s" % str(args))
    
        
    # Read the config file
    config = ConfigParser.ConfigParser()  
    try:
        config_file = open( options.config)
    except IOError, e:
        logger.critical( "Failed to open config file '%s'"%options.config)
        logger.critical( e)
        logger.critical( "Aborting")
        sys.exit(1)
        
    config.readfp(config_file)

    # TODO: Trap exceptions for missing config options
    INSTRUMENT = config.get("Beamline Config", "INSTRUMENT")
    BEAMLINE_PREFIX = config.get("Beamline Config", "BEAMLINE_PREFIX")
    PV_PREFIX = BEAMLINE_PREFIX + ":CS:"
    
    # ConfigParser doesn't recognize lists of items, so what we get back is a
    # single string that we split into a list ourselves
    pv_list_str = config.get("Beamline Config", "PROCESS_VARIABLES")
    PROCESS_VARIABLES.extend( [i.strip() for i in pv_list_str.split(',')])
    
    
    plugin_dirs = []  # List that holds the directories we'll search for plugins
    if config.has_option("System Config", "PLUGINS_DIRS"):
        plugdir_list_str = config.get("System Config", "PLUGINS_DIRS")
        plugin_dirs.extend( [i.strip() for i in plugdir_list_str.split(',')])
        
    # Done with the config file


    # Import our plugins
    
    # The default plugin dir is a directory named 'plugins' in the same dir
    # as our main .py file.
    exec_paths = sys.argv[0].split(os.sep)
    if (len(exec_paths)==1):
        # no actual path in argv[0].  Use './plugins'
        plugin_dirs.append("./plugins")
    else:
        exec_paths[-1] = 'plugins'
        plugin_dirs.append( os.sep.join( exec_paths))

    # Add any plugin dirs that were specified on the command line        
    if options.plugin_dirs != None:
        plugin_dirs.extend(options.plugin_dirs)
    
    logger.info( "Plugin directories: %s" % str( plugin_dirs))
    
    chunk_regex = {}
    post_regex = {}
    import_plugins( plugin_dirs, chunk_regex, post_regex)
    
    
    
    # Now match all the requested PV names to a pattern in chunk_regex or
    # post_regex and build up the PV_Functions_Chunk and PV_Functions_Post
    # dictionaries.
    for pv_name in PROCESS_VARIABLES:
        function_found = False
        for r in chunk_regex:
            if r.match(pv_name):
                function_found = True
                PV_Functions_Chunk[pv_name] = chunk_regex[r]
                break
        
        if function_found:
            continue;  # don't bother searching the post_regex dict
            
        for r in post_regex:
            if r.match(pv_name):
                function_found = True
                PV_Functions_Post[pv_name] = post_regex[r]
                break
        
        if not function_found:
            logger.error( "Could not match PV '%s' to any calculation function"%pv_name)
            
    
    # TODO: Verify that a requested PV only matches a single callable 
    
    

    # Note: if processing or post-processing algorithms require an
    # accumulation workspace, then the returned tuple will look like:
    # (accumWS, outWS, somestr, monitor_alg)
    sld_return = StartLiveData(
        Instrument = INSTRUMENT,
        # This "instrument" actually ends up trying to connect to localhost:31415, so is
        # good for testing
        AccumulationMethod = 'Add',
        #AccumulationMethod = 'Append',
        #AccumulationMethod = 'Replace',
        #EndRunBehavior = 'Stop',
        EndRunBehavior = 'Rename',
        PreserveEvents = True,
        #PreserveEvents = False,
        FromNow = True,
        ProcessingAlgorithm = 'ChunkProcessing',
        #ProcessingScript = processing_script,
        #ProcessingProperties = 'Params=10000,1000,40000',
        PostProcessingAlgorithm = 'PostProcessing',
        #    PostProcessingProperties = 
        #UpdateEvery = 5,
        UpdateEvery = 1,
        OutputWorkspace = 'myoutWS',
        AccumulationWorkspace = 'accumWS',
        )
    
    server = SimpleServer()

    server.createPV(PV_PREFIX, build_pvdb())
    driver = myDriver()

    #for i in range(100):
    while True:
        # process CA transactions
        server.process(0.1)
            
    # There's currently no clean way to shut this program down.  The cancel()
    # method isn't currently exposed to python algorithms (though that will
    # be changing shortly) and even if it was, ther's basically no way to
    # call it.  Ctrl-C is the best I can think of for now.
    # Since this code will eventually be a daemon process, that's probably 
    # an acceptable solution.


if __name__ == '__main__':
    main()
