#StatisticsService

This is a python application that uses the Mantid framework to listen to an ADARA stream and update EPICS process variables with various data about the stream.

##Plugin Architecture Description
The process variables that this program outputs are calculated by means of individual 'calculation functions'.  This program uses a plugin-based architecture that makes it easy to add more calculation functions (and thus compute and output new process variables).  What follows is a description of the plugin architecture:

1. Plugins are stored in designated plugins directories.  By default, the program searches for a directory called 'plugins' under the directory that contains the main .py file.  Plugin directories can also be specified on the command line or in the configuration file. 
2. At program start, all plugin dirs are scanned for .py files.
3. Any .py file that is found is treated as a module and imported.  The module's 'register_pvs' function is called.  (It's a requirement that this function exists.  The program will log a warning if it doesn't.)
4. The register_pvs function returns a tuple of of 3 dictionaries.  The first two dicts map a regular expression to a callable that will calculate the value for any PV who's name matches that regular expression. The first dict in the tuple is for values that are calculated during the chunk processing.  The second dict is for values that are calculated during the post processing stage.  The remaining dictionary maps a regular expression to a callable that will be used to generate an EPICS database record for each PV.  (For more details, see the SoftIOC section below.)
5. It's up to the register function to do any initialization prior to returning.  (ie: set some global values, instantiate a callable object, etc..)
6. The callables returned in the dictionaries should all use the `**kwargs` calling idiom so that they can safely ignore any keyword params that they don't need.  See below for the list of keywords that will be passed to all callables.

*Notes:*
* Most of these 'plugins' will actually be included on all systems.  How do we actually package all these files up?  Python eggs?
* Can we make this dynamic at a later date (ie: constantly scan the plugin dirs for new files and load them when they're discovered?)

##The SoftIOC Executable
This program is an EPICS Channel Access Client, not a server.  It relies on the 'softIoc' executable (which is included in the EPICS software distribution) for CA server duties.  As such, it has a command line option to create the .cmd and .db files that the softIoc executable needs.

In addition to their calculation functions, all plugins must provide a function (or functions) that will generate the appropriate text to describe their PV's db records.  These descriptions are what is written to the .db file that the softIoc executable will read when it starts.

##Keyword Parameters Passed To The PV Calc Functions

The following keywords are passed to every PV calculation function when it is called:
* chunkWS: `IEventWorkspace` - an event workspace containing the data that's arrived since the last call
* accumWS: `IEventWorkspace` - an event workspace containing all the data for the current run
* pv_name: `string` - The name of the process variable to be calculated. (Needed for cases where the same function may calculate more than 1 process variable.)
* run_num: `int` - the current run number.  May be 0 if we're between runs.
* logger_name: `string` - the name of the logger to use (if you want log messages to appear in the same location as the main program)

Note: chunkWS and accumWS are mutually exclusive.  One is guaranteed to be None.  They're both passed so that the same calc function could be used for both chunk processing and post processing. Not sure if there's any reason for a calc function to do this, but it's at least possible.

##Keyword Parameters Passed To The DB Record Generation Functions

The following keywords are passed to every db record generation function when it is called:
* pv_name: 'string' - The name of the process variable who's db record is being created.

## PyEpics Library
The code under lib/epics is actually from the PyEpics library, available [here](http://pyepics.github.io/pyepics/overview.html).  It is licensed under the Epics Open License and the copyright is held by Matthew Newville <newville@cars.uchicago.edu> CARS, University of Chicago.
