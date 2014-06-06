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

from epics import PV

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
# that calculate their values and another to map PV names their associated
# epics.PV object.  Also need a list to hold the PV names the user wants us to 
# calculate.
# 
# TODO: Find a way avoid having to use global variables here.  The problem
# is that they are used by the Algorithm instances, and those classes are
# instantiated down in the Mantid code so I can't pass anything to their
# constructors...
PV_Functions_Chunk = {}
PV_Functions_Post = {}
PV_Objs = {}
PROCESS_VARIABLES = []

# Another global: The name of the logger object.  Using a global so that all
# the different functions can log to the same location. (And also the two
# Algorithm objects can also use it.)
# The 'pythonic' way is to use the name of the module, but in this case 
# 'main' is a lousy name for a logger.
LOGGER_NAME="MantidStats"


def init_PV_objs( pv_prefix):
    '''
    Create PV objects for each variable in PROCESS_VARIABLES
    '''
    
    #logger = logging.getLogger(LOGGER_NAME)
    for name in PROCESS_VARIABLES:
        PV_Objs[name] = PV( pv_prefix + name)
    
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
                        
        for pv_name in PROCESS_VARIABLES:
            if pv_name in PV_Functions_Chunk:
                
                if not PV_Objs[pv_name].connect():
                    logger.error( "PV '%s' is not connected!"%PV_Objs[pv_name].pvname)
                    
                # Note: Always use keyword args when calling the PV functions.
                # Positional arguments are not allowed because we didn't want
                # to force a particular function signature on everyone.
                # Instead, we document what keywords are passed and what they
                # mean; authors of PV functions can pick and choose which
                # keywords are important to their particular function. 
                PV_Objs[pv_name].value =  \
                    PV_Functions_Chunk[pv_name]( chunkWS = inputWS,
                                                 accumWS = None,
                                                 pv_name = pv_name,
                                                 run_num = inputWS.getRunNumber(),
                                                 logger_name = LOGGER_NAME
                                                )
                # Note: If you change the list of keyword parameters, be sure
                # to update README.md!!!
            #else:
                #logger.error( "No function for calculating value of %s"%pv_name)
            
        # Since we don't modify the data in any way, we don't need to copy
        # the input over to the output workspace.
        logger.debug( "ChunkProcessing algorithm complete")
            
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
                        
        for pv_name in PROCESS_VARIABLES:
            if pv_name in PV_Functions_Post:
                
                if not PV_Objs[pv_name].connect():
                    logger.error( "PV '%s' is not connected!"%PV_Objs[pv_name].pvname)
                    
                # Note: Always use keyword args when calling the PV functions.
                # Positional arguments are not allowed because we didn't want
                # to force a particular function signature on everyone.
                # Instead, we document what keywords are passed and what they
                # mean; authors of PV functions can pick and choose which
                # keywords are important to their particular function.
                PV_Objs[pv_name].value =  \
                    PV_Functions_Post[pv_name]( chunkWS = None,
                                                accumWS = inputWS,
                                                pv_name = pv_name,
                                                run_num = inputWS.getRunNumber(),
                                                logger_name = LOGGER_NAME
                                              )
                # Note: If you change the list of keyword parameters, be sure
                # to update README.md!!!
            #else:
                #logger.error( "No function for calculating value of %s"%pv_name)
        
        # Last step - copy the input over to the output
        #outputWS = mtd[ self.getPropertyValue("OutputWorkspace")]
        #outputWS = inputWS
        # In theory, we shouldn't have to copy the input to the output if we
        # don't modify the data, but for some reason, we do.  Also, the
        # outputWS = inputWS line should suffice, but again for some reason
        # it doesn't.  Russell is looking in to both these problems.  In the
        # meantime, clone() works fine.
        inputWS.clone(OutputWorkspace = self.getPropertyValue("OutputWorkspace"))
        logger.debug( "PostProcessing algorithm complete")
        
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
    
    logger = logging.getLogger( LOGGER_NAME)
    
    if is_restart:
        logger.error( "Restarting the live listener algorithm (which " +
                      "implies that the algorithm crashed somehow).")
        
    # Check to see if we need the PostProcessing algorithm.  Not calling
    # it will save a fair amount of CPU time.  Also, if we don't need
    # it, then we don't need to preserve events, which could save a fair
    # amount of RAM, especially on long running runs.  (We have to set
    # the value to True in order to force the workspace passed to the
    # PostProcessing alg to be an EventWorkspace.)
    if len( PV_Functions_Post):
        post_proc_alg = 'PostProcessing'
        preserve_events = True
    else:
        post_proc_alg = None
        preserve_events = False
    
    # Note: if processing or post-processing algorithms require an
    # accumulation workspace, then the returned tuple will look like:
    # (accumWS, outWS, somestr, monitor_alg)
    sld_return = StartLiveData(             # @UndefinedVariable
        Instrument = instrument,
        AccumulationMethod = 'Add',
        #AccumulationMethod = 'Append',
        #AccumulationMethod = 'Replace',
        #RunTransitionBehavior = 'Stop',
        #RunTransitionBehavior = 'Rename',
        RunTransitionBehavior = 'Restart',
        PreserveEvents = preserve_events,
        #PreserveEvents = False,
        FromNow = True,
        #FromNow = False,  # defaults to True, so have to explicitly set it to
                          # False if you want to use one of the other options
        #FromStartOfRun = True,
        # TODO: I'm not sure about using 'FromStartOfRun'.  If the service 
        # in the middle of a run, replaying from the start makes sense.
        # However, if we're not in the middle of a run when the live listener
        # is started, then this option will cause the listener to ignore all
        # data until a run does start...
        ProcessingAlgorithm = 'ChunkProcessing',
        #ProcessingScript = processing_script,
        #ProcessingProperties = 'Params=10000,1000,40000',
        PostProcessingAlgorithm = post_proc_alg,
        #    PostProcessingProperties = 
        #UpdateEvery = 5,
        UpdateEvery = 1,
        OutputWorkspace = 'myoutWS',
        AccumulationWorkspace = 'accumWS',
        )
    
    mld_alg = sld_return[-1] # last element in sld_return is the MonitorLiveData algorithm
    # Wait for the mld algorithm to actually start
    # TOD: Put some kind of timeout in here!
    if not mld_alg.isRunning():
        logger.debug( "Waiting for MonitorLiveData algorithm to start")
        time.sleep(0.1)
    
    logger.debug( "MonitorLiveData algorithm now running")
    return mld_alg   
    
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
    
    # Create the PV objects
    init_PV_objs( PV_PREFIX) 
    
    # Attempt the start the mantid live listener
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
    
    if options.debug:
        # Register signal handlers for SIGUSR1 & SIGUSR2 to do some
        # useful debuggy stuff
        try:
            # A package useful for debugging memory leaks.
            # If it doesn't exist, just keep going.  
            import objgraph
            # register a signal handler to dump some debug info when we send it a sigusr1
            def sigusr1_handler(signal, frame):
                logger.info( "######SIGUSR1 Received######")
                # Unfortunately, the objgraph functions use 'print', so I haven't figured out
                # how to get them into the logger...
                objgraph.show_most_common_types()
                objgraph.show_growth( limit=3)
                logger.info( "###########################")
            signal.signal( signal.SIGUSR1, sigusr1_handler)
        except ImportError:
            logger.warning( "Skipping SIGUSR1 handler because 'objgraph' package wasn't found")
    
        # register a signal handler to dump us into the debugger when we send a sigusr2
        def sigusr2_handler(sig, frame):
            import pdb
            pdb.Pdb().set_trace(frame)
        signal.signal(signal.SIGUSR2, sigusr2_handler)

    
    while keep_running and not sigterm_received:
    #for i in range(25):
        try:
            if not mld_alg.isRunning():
                try:
                    mld_alg = start_live_listener(INSTRUMENT) 
                except RuntimeError, e:
                    # Most exceptions that the live listener will throw are caught one level up and just
                    # cause the monitor algorithm to end.  If an exception actually propagates all the
                    # way out to this level, something really bad has happened.
                    logger.critical( "Caught RuntimeError starting live listener: %s"%e)
                    logger.critical( "It may be worthwhile to check the Mantid log file for more details")
                    logger.critical( "Aborting.")
                    sys.exit( -1)
            
            # Assuming everything is running normally, we don't want to
            # spinlock the CPU...
            time.sleep(2.0) 
        except KeyboardInterrupt:
            logger.debug( "Keyboard interrupt")
            keep_running = False # Exit from the loop
    
            
    
    # Stop the monitor live data algorithm (and wait for it to actually stop)
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
