'''
Created on Jan 30, 2014

@author: xmr
'''


'''
TODO List:
- Figure out how best to store individual PV calc callables (or classes) - probably separate .py files in a package?
- Figure out how to allow wildcards in the mapping from PV name to callable.  (So, for example, a single callable 
  handle multiple beam monitor PV's) - Use RegEx's - Python has good support for them
- Figure out how to automatically import all PV calc functions (will from xxxx import * work?)
- Figure out how to automatically register the functions when they're imported
- Document the keyword params that will be passed to the callables
- There is a perceptible amount of time between the ChunkProcessing and PostProcessing algorithms.  Specifically, it
  was not uncommon for the EVTCNT and EVTCNT_POST to differ when polled with caget.  Need to discuss this with some
  of the instrument scientists and determine if that could cause problems.
- Figure out how to daemonize python programs.  I think there's a package for that...
- There a lot more to the pcaspy library to figure out.  In particular, running camonitor (from another terminal)
  doesn't show the values updating, though repeatedly running caget does.  Need to figure out why. 
- Figure out a way to specify the mantid library location in the config file (the sys.path.append() and import
  statements are normally executed well before the config file is parsed...)


Config related tasks:
- Figure out global config options ( update rate for live listener, preserve events)
- Figure out beamline config options (beamline name, beamline prefix, which PV's to calculate)
- Should the two sets of config options be in a single config file? Probably...
- Make the code robust enough to handle improperly written config files (at least fail gracefully)

'''

'''
A possible plugin architecture for the PV calc functions:
1) Have a designated 'plugin' directory. (Possibly more than one: a system
   plugins dir and and user plugins dir??  Also have a command line option
   to specify dir(s).)
2) At program start, plugin dir(s) are scanned for files.
3) Any .py file is loaded (how, exactly?  need to look this up) and a
   'register_pvs' function is called.  (It's a requirement that this function
   exists.  Program will throw and exception - or at least log a warning - if
   it doesn't)
4) register_pvs function returns a tuple of of 2 dictionaries.  Each dict
   maps a PV name to a callable that will calculate the value for that PV.
   The first dict in the tuple is for values that are calculated during the
   chunk processing.  The second dict is for values that calculated during
   the post processing.  The contents of the 2 dicts will be added to the
   top-level PV_Functions_* dicts.
5) It's up to the register function to do any initialization prior to 
   returning.  (ie: set some global values, instantiate a callable object,
   etc..)
6) The callables returned in the dictionaries should all use the **kwargs
   calling idom so that they can safely ignore any keyword params that they
   don't need.  See below for the list of keywords that will be passed to all
   callables.   
   
Notes:
- Will the callables returned by the register_pvs functions be accessible
  at the top level?
- Most of these 'plugins' will actually be included on all systems.  How
  do we actually package all these files up?  Python eggs?
- Can we make this dynamic at a later date (ie: constantly scan the
  plugin dirs for new files and load them when they're discovered?)
'''


'''
Keywords passed to the pv calc functions:

chunkWS - IEventWorkspace - an event workspace containing the data that's
          arrived since the last call
accumWS - IEventWorkspace - an event workspace containing all the data for
          the current run
run_num - int - the current run number.  May be 0 if we're between runs.

Note: chunkWS and accumWS are mutually exclusive.  One is guaranteed to be
None.  They're both passed so that the same calc function could be used for
both chunk processing and post processing. Not sure if there's any reason for
a calc function to do this, but it's at least possible. 
'''

import sys
import os

from optparse import OptionParser
import ConfigParser

#sys.path.append(os.environ['MANTIDPATH'])
#MANTIDPATH env var should be set by the Mantid installer.
#For now, just use a hard-coded path 
sys.path.append('/home/xmr/mantid-build/bin')

from mantid.simpleapi import *
from mantid.api import IEventWorkspace
from mantid.api import Run
from mantid.api import PythonAlgorithm, AlgorithmFactory, WorkspaceProperty
from mantid.kernel import Direction, logger

# pcaspy library for EPICS stuff
# Again, using a hard-coded path
sys.path.append('/opt/pcaspy/lib64/python2.7/site-packages/pcaspy-0.4.1-py2.7-linux-x86_64.egg')
from pcaspy import SimpleServer, Driver

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


# -----------------------------------------------------------------------------
# This is code for generating each particular PV.
# Need to figure out how to organize this and automatically register it with
# the PV_Functions and PV_Values dictionaries
#
# Note the function signature:  keyword arguments that we know we'll need are
# mandatory.  The **extra_kwargs is there to soak up any other keywords the
# main program may pass.  The main program is guaranteed to pass all arguments
# as keyword args.  It will not use positional args.

def calc_evtcnt( chunkWS, **extra_kwargs):
    '''
    Calculates the EVTCNT process variable.
    '''
    
    # Note: We're operating on the chunkWS, which means we need to keep a
    # running sum of the events in a static variable and add the events
    # in chunkWS to it.  (And reset it to 0 when the run # changes.)
    #
    # Yes, this would be much easier to implement in the post-processing
    # stage.  I'll work on that next.
    
    # The try...except paragraph initializes a couple of attributes on
    # the function.  This is the python equivalent of static variables
    try:
        calc_evtcnt.run_num
        calc_evtcnt.events
    except AttributeError:
        calc_evtcnt.run_num = chunkWS.getRunNumber()
        calc_evtcnt.events = 0
        
    if calc_evtcnt.run_num != chunkWS.getRunNumber():
        # new run - reset the event count
        calc_evtcnt.events = 0
        calc_evtcnt.run_num = chunkWS.getRunNumber()
        
    calc_evtcnt.events += chunkWS.getNumberEvents()
    return calc_evtcnt.events
    
    
# Register our PV function
PV_Functions_Chunk['EVTCNT'] = calc_evtcnt
      
# -----------------------------------------------------------------------------

def calc_runnum( chunkWS, **extra_kwargs):
    '''
    Calculates the RUNNUM process variable.
    '''
    
    # This one is about as simple as it gets    
    return chunkWS.getRunNumber()   
    
# Register our PV function
PV_Functions_Chunk['RUNNUM'] = calc_runnum
      
# -----------------------------------------------------------------------------

def calc_protoncharge( chunkWS, **extra_kwargs):
    '''
    Calculates the PROTONCHARGE process variable.
    '''
    
    # The try...except paragraph initializes a couple of attributes on
    # the function.  This is the python equivalent of static variables
    try:
        calc_protoncharge.run_num
        calc_protoncharge.accum_charge
    except AttributeError:
        calc_protoncharge.run_num = chunkWS.getRunNumber()
        calc_protoncharge.accum_charge = 0
        
    if calc_protoncharge.run_num != chunkWS.getRunNumber():
        # new run - reset the accumulated charge
        calc_protoncharge.accum_charge = 0
        calc_protoncharge.run_num = chunkWS.getRunNumber()
    
    run = chunkWS.run()
    # For reasons that are unclear, calling run.getProtonCharge() causes the program to
    # crash with an error about unknown property "gd_prtn_chrg" 
    if run.hasProperty( 'proton_charge'):
        # the proton_charge property is the charge for each pulse.  We need to
        # sum all of those charge values
        p_charge = run.getProperty('proton_charge')
        for n in range( p_charge.size()):
            calc_protoncharge.accum_charge += p_charge.nthValue(n)
    
    return calc_protoncharge.accum_charge
        
    
# Register our PV function
PV_Functions_Chunk['PROTONCHARGE'] = calc_protoncharge
      
# -----------------------------------------------------------------------------



# -----------------------------------------------------------
# HACK!!!
# I want to try get the event counts from the post-processing step
# This value should be the same as what's produced from the chunk
# processing, but without the necessity of doing the accumulation myself
def calc_evtcnt_post( accumWS, **extra_kwargs):
    '''
    Calculates the EVTCNT_POST process variable.
    '''
        
    return accumWS.getNumberEvents()

PV_Functions_Post['EVTCNT_POST'] = calc_evtcnt_post
# ------------------------------------------------


def build_pvdb():
    '''
    Generates the pvdb dictionary to pass to createPV()
    '''
    pvdb = { }
    
    for name in PROCESS_VARIABLES:
        pvdb[name] = { 'prec' : 5}
        # for now, all variables will have a precision of 5
        # There's a lot of other fields we could add, so we
        # might want to make this more customizable.
    
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
        logger.information( "Running the ChunkProcessing algorithm")
    
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
                                                        run_num = inputWS.getRunNumber()
                                                      )
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
        logger.information( "Running the PostProcessing algorithm")
        
        # Call each PV's calculation function
        inputWS = self.getProperty("InputWorkspace").value
        if not isinstance(inputWS, IEventWorkspace):
            logger.error( "InputWorkspace was a type '%s' instead of an IEventWorkspace"%type(inputWS).__name__)
            logger.error( "Attempting to continue, but this is likely to cause Mantid to crash eventually.")
                        
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
                                                       run_num = inputWS.getRunNumber()
                                                     )
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




def main():
    '''
    Parse the command line options and config file, then start up the mantid
    live listener and begin exporting the requested process variables.
    '''
    
    # First, parse the command line options
    parser = OptionParser()
    parser.add_option("-f", "--config_file", dest="config",
                      help="the name of the configuration file",
                      default="")
    
    parser.set_defaults(config="mantidstats.conf")  
    (options, args) = parser.parse_args()
    
    # There shouldn't be any extra args
    if len(args):
        logger.warning( "Extraneous command line arguments: %s" % str(args))
    
    # Read the config file
    # TODO: Trap exceptions!
    config = ConfigParser.ConfigParser()
    config.read( options.config)
    INSTRUMENT = config.get("Beamline Config", "INSTRUMENT")
    BEAMLINE_PREFIX = config.get("Beamline Config", "BEAMLINE_PREFIX")
    PV_PREFIX = 'SNS:' + BEAMLINE_PREFIX + ":MSS:"
    
    # ConfigParser doesn't recognize lists of items, so what we get back is a
    # single string that we split into a list ourselves
    pv_list_str = config.get("Beamline Config", "PROCESS_VARIABLES")
    PROCESS_VARIABLES.extend( [i.strip() for i in pv_list_str.split(',')])
    
    # Done with the config file



    # TODO: Validate the PROCESS_VARIABLES list (ie: make sure we know how
    # to calculate every requested PV)



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