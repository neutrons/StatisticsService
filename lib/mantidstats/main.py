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
- Figure out a way to specify the mantid library location in the config file (the sys.path.append() and import
  statements are normally executed well before the config file is parsed...)
- If we don't have any PV's that require the post-processing step, then don't set the 'PreserveEvents' and
  'PostProcessingAlgorithm' parameters in StartLiveListener()  (saves memory and CPU cycles down in Mantid)
- Add code to handle improper regex strings in plugin definitions
- Define one or more exceptions for the calculation functions to throw when
  they encounter errors.  Have the ChunkProcessing and PostProcessing
  algorithms trap the exceptions and set the appropriate EPICS error flags for
  the PV 
- Need to remove the hard-coded path extension for importing pcaspy
- Add units to the entries in pvdb
- Figure out if we should add the asyn field to entries in pvdb

Config related tasks:
- Figure out global config options ( update rate for live listener, preserve events, locations for plugin dirs?)
- Figure out beamline config options (beamline name, beamline prefix, which PV's to calculate)
- Make the code robust enough to handle improperly written config files (at least fail gracefully)
- Allow users to specify the update rate (ie: the value of the 'scan' field in pvdb) for each PV

'''

import sys
import signal
import os
import re  # regex processing for the PV calculation callables
import time  # for the sleep() function

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
    import mantid.kernel
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
from pcaspy import SimpleServer, Driver, Alarm, Severity  # @UnresolvedImport

# -------------------------------------------------------------------------
# Commented out for now because pcaspy package doesn't play nice with
# the daemon package
# Try to use the daemon package.  But continue anyway if it's not available
#NO_DAEMON_PKG=False
#try:
#    import daemon
#except ImportError:
#    NO_DAEMON_PKG=True
#-----------------------------------------------------------------------------

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
        logger = logging.getLogger( LOGGER_NAME)
        logger.debug( "Read request for PV: %s" % reason)
        try:
            value = PV_Values[reason]   # reason is the name of the PV (without
                                        # the prefix)
            self.setParamStatus( reason, Severity.NO_ALARM, Alarm.NO_ALARM)
        except KeyError:
            # Value hasn't been calculated (yet?)
            value = None
            #value = self.getParam(reason)
            self.setParamStatus( reason, Severity.INVALID_ALARM, Alarm.UDF_ALARM)
                   
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
        # meantime, clone() works fine.
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
        
def start_live_listener( instrument, is_restart = True):
    '''
    Start up the Live Listener algorithm.  If is_restart is true, write an
    error message to the log.  (We'd only ever restart if the listener aborted
    for some reason.)
    '''
    
    if is_restart:
        logger = logging.getLogger( LOGGER_NAME)
        logger.error( "Restarting the live listener algorithm (which " +
                      "implies that the algorithm crashed somehow).")
    
    # Note: if processing or post-processing algorithms require an
    # accumulation workspace, then the returned tuple will look like:
    # (accumWS, outWS, somestr, monitor_alg)
    sld_return = StartLiveData(             # @UndefinedVariable
        Instrument = instrument,
        AccumulationMethod = 'Add',
        #AccumulationMethod = 'Append',
        #AccumulationMethod = 'Replace',
        #RunTransitionBehavior = 'Stop',
        RunTransitionBehavior = 'Rename',
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
    
    return sld_return[-1]  # last element in sld_return is the MonitorLiveData algorithm
    
def write_pidfile( filename):
    pid = os.getpid()
    pidfile = open( filename, "w")
    pidfile.write("%d\n"%pid)
    pidfile.close()
    

def main():
    '''
    Parse the command line options and set up the logging system.  Then 
    decide whether to become a daemon process or remain in the foreground.
    '''
    
    # First, parse the command line options
    parser = OptionParser()
    parser.add_option("-f", "--config_file", dest="config",
                      help="the name of the configuration file",
                      metavar="CONFIG_FILE",
                      default='/etc/mantidstats.conf')
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
    parser.add_option("-p", "--pidfile", metavar="PIDFILE",
                       help="Write the process ID to the specified file")
# Disabling daemoninzing for now because the pcaspy package doen't work properly inside a daemon
#    parser.add_option("", "--no_daemon", dest="no_daemon",
#                      help="Don't start up as a daemon process - remain in the foreground",
#                      action="store_true")
  
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

        formatter = logging.Formatter('%(name)s [%(process)d]: %(levelname)s - %(message)s')
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


# ---------------------------------------------------------------------------
# Daemonization disabled until we can figure out how to make pcaspy work
# correctly when it's a daemon    
#    # Should we fork and become a daemon?
#    if not options.no_daemon:
#        if NO_DAEMON_PKG == False:
#            logger.debug( "About to fork to background")
#            daemon_context = daemon.DaemonContext()
#            daemon_context.open()
#            logger.debug( "Running as a daemon")  # for reasons that are unclear, this debug statement never shows up!
#        else:
#            logger.warning( "Python daemon library not found.  Cannot daemonize.  Continuing in the foreground.")
#-----------------------------------------------------------------------------
            
    logger.debug( "Calling main_continued()")
    main_continued( options)
    
    
# The main_continued() function was split off of main() so that everything in
# main_continued() can run in the background process if we are running in
# daemon mode.  
def main_continued( options):    
    '''
    Parse the config file, then start up the mantid live listener and begin
    exporting the requested process variables.
    '''
    
    logger = logging.getLogger( LOGGER_NAME)
    
    if options.pidfile:
        logger.debug( "Writing pid file to %s"%options.pidfile)
        write_pidfile( options.pidfile)
        
    # Read the config file
    config = ConfigParser.ConfigParser()  
    try:
        config_file = open( options.config)
    except IOError, e:
        logger.error( "Failed to open config file '%s'"%options.config)
        logger.error( e)
        logger.error( "Trying ./mantidstats.conf as a last resort")
        try:
            config_file = open( "./mantidstats.conf")
        except IOError:
            logger.critical( "Failed to open any config file.")
            logger.critical( "Aborting")
            sys.exit(1)
        
    config.readfp(config_file)

    # TODO: Trap exceptions for missing config options
    INSTRUMENT = config.get("Beamline Config", "INSTRUMENT")
    BEAMLINE_PREFIX = config.get("Beamline Config", "BEAMLINE_PREFIX")
    PV_PREFIX = BEAMLINE_PREFIX + ":CS:"
    
    # Check to see if we need to override Mantid's default facilities
    if config.has_option("Beamline Config", "FACILITY_FILE"):
        facility_file = config.get("Beamline Config", "FACILITY_FILE")
        logger.info( "Replacing default Mantid facilities file with: '%s'"%facility_file)
        mantid.kernel.config.updateFacilities( facility_file)
        
    # Verify that Mantid recognizes the instrument
    if (INSTRUMENT != "SNSLiveEventDataListener"): 
    # SNSLiveEventDataListener isn't a valid instrument, but it is hard-coded
    # into the Mantid code for debug purposes, so we'll allow it here, too.
        try:
            inst_info = mantid.kernel.config.getInstrument( INSTRUMENT)
        except:
            logger.critical( "Couldn't find instrument named '%s'"%INSTRUMENT )
            logger.critical( "Verify that the 'INSTRUMENT' parameter is " + \
                             "specified properly in the config file and that " + \
                             "the modified facilities file (if used) is also " + \
                             "correct.")
            logger.critical( "Aborting")
            sys.exit(1)
        logger.debug( "SMS Server: %s"%inst_info.instdae())
    
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
    
    server = SimpleServer()
    server.createPV(PV_PREFIX, build_pvdb())
    driver = myDriver()  # @UnusedVariable
    # Note: The Driver base class does some interesting things with
    # __metaclass__ to automatically register itself with the
    # SimpleServer.  Thus, the fact that the fact that the driver object
    # is never referenced again is not an error.

    try:
        mld_alg = start_live_listener( INSTRUMENT, False)
    except RuntimeError, e:
        # If we can't even start the live listener, there probably isn't much
        # point in continuing.
        # Experience thus far says this probably happened becase we can't
        # contact the SMS daemon.
        logger.critical( "Caught RuntimeError starting live listener: %s"%e)
        logger.critical( "It may be worthwhile to check the Mantid log file for more details")
        logger.critical( "Aborting.")
        sys.exit( -1)

    keep_running = True
    
    # register a signal handler so we can exit gracefully if someone kills us
    global sigterm_received
    sigterm_received = False
    def sigterm_handler(signal, frame):
        global sigterm_received
        logger.debug( "SIGTERM received")
        sigterm_received = True
    signal.signal(signal.SIGTERM, sigterm_handler)
    
    while keep_running and not sigterm_received:
    #for i in range(25):
        try:
            # process CA transactions
            server.process(1.0)
            # The value is supposedly in seconds (according to the docs), but
            # exactly what it means is unclear.  It doesn't seem to have any
            # bearing on how quickly the function returns, but it does seem to
            # effect how often the PV's are updated when viewed from an external
            # camonitor process.
            
            # verify the live listener is still running.  Restart it if not.
            if not mld_alg.isRunning():
                try:
                    time.sleep(2.0) # The delay will hopefully keep us from 
                                    # flooding the syslog if we get into a state
                                    # where the monitor alg keeps dieing
                                    # immediately after stating up.
                    mld_alg = start_live_listener(INSTRUMENT) 
                except RuntimeError, e:
                    # Most exceptions that the live listener will throw are caught one level up and just
                    # cause the monitor algorithm to end.  If an exception actually propagates all the
                    # way out to this level, something really bad has happened.
                    logger.critical( "Caught RuntimeError starting live listener: %s"%e)
                    logger.critical( "It may be worthwhile to check the Mantid log file for more details")
                    logger.critical( "Aborting.")
                    sys.exit( -1)
        except KeyboardInterrupt:
            logger.debug( "Keyboard interrupt")
            keep_running = False # Exit from the loop
    
            
    
    # Stop the live listener algorithm (and wait for it to actually stop)
    if mld_alg.isRunning():
        mld_alg.cancel()
        while mld_alg.isRunning():
            time.sleep(0.1)
            
    logger.info( "Exiting.")
    
    # TODO: Are there any other shutdown/cleanup tasks to do here?   
    return  # end of main_continued()
    
            
    # There's currently no clean way to shut this program down.  The cancel()
    # method is now exposed to python algorithms, but there's basically no 
    # good way to call it.  Trapping a Ctrl-C is the best I can think of for
    # now.  Since this code will normally run as a daemon process, that's
    # probably an acceptable solution.


if __name__ == '__main__':
    main()
