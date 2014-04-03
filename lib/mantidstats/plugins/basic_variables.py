'''
Created on Mar 10, 2014

@author: xmr

Holds calculation functions for some of the more basic process variables
'''

# -----------------------------------------------------------------------------

def calc_evtcnt( chunkWS, **extra_kwargs):
    '''
    Calculates the EVTCNT process variable.
    '''
    # Note: We're operating on the chunkWS, which means we need to keep a
    # running sum of the events in a static variable and add the events
    # in chunkWS to it.  (And reset it to 0 when the run # changes.)
        
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

# -----------------------------------------------------------------------------

def calc_runnum( run_num, **extra_kwargs):
    '''
    Calculates the RUNNUM process variable.
    '''
    
    # This one is just stupid simple...    
    return run_num   

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
        
# -----------------------------------------------------------

def calc_evtcnt_post( accumWS, **extra_kwargs):
    '''
    Calculates the EVTCNT_POST process variable.
    '''
        
    return accumWS.getNumberEvents()

# -----------------------------------------------------------

class calc_beam_mon_cnt:
    '''
    Calculate values for beam monitor event count process variables
    '''
    
    def __init__(self):
        
        # create all the attributes that the __call__() function is going to
        # need
        
        # Since this class will work for multiple PV names, we use these
        # dicts map a particular name to its associated value 
        self._counts = {} # the accumulated beam monitor counts 
        self._last_run_num = {} # The previous run number (so we know when to
                                # reset the counts.
                                
    def __call__( self, chunkWS, pv_name, run_num, **kwargs):
        # Sanity check pv_name
        # Note: expects the name to be something like M1CNT, M2CNT, M99CNT, etc...
        if pv_name[0] != 'M' or pv_name[-3:] != 'CNT':
            # HACK!! What should we do here? Throw an exception?
            return -1
        
        try:
            int( pv_name[1:-3])
        except ValueError:  # couldn't figure out the monitor number...
            # HACK!! Again, should probably throw some other exception
            return -1
        
        # initialize the counts and last run num, if necessary
        if not pv_name in self._counts:
            self._counts[pv_name] = 0;
            self._last_run_num[pv_name] = run_num
        
        # do we need to reset the accumulated count?
        if run_num != self._last_run_num[pv_name]:
            self._counts[pv_name] = 0;
            self._last_run_num[pv_name] = run_num
        
        
        prop_name = "monitor" + pv_name[1:-3] + "_counts"
        if chunkWS.run().hasProperty( prop_name):
            prop = chunkWS.run().getProperty( prop_name)
            self._counts[pv_name] += prop.value
            return self._counts[pv_name]
        else:
            # HACK: should we throw an exception in this case?
            return -1
# -----------------------------------------------------------    

def calc_beam_mon_cnt_post( accumWS, pv_name, **kwargs):
    '''
    Calculate values for beam monitor event count process variables
    '''
    
    # Sanity check pv_name
    # Note: expects the name to be something like M1CNT, M2CNT, M99CNT, etc...
    if pv_name[0] != 'M' or pv_name[-8:] != 'CNT_POST':
        # HACK!! What should we do here? Throw an exception?
        return -1
    
    try:
        int( pv_name[1:-8])
    except ValueError:  # couldn't figure out the monitor number...
        # HACK!! Again, should probably throw some other exception
        return -1
    
    prop_name = "monitor" + pv_name[1:-8] + "_counts"
    if accumWS.run().hasProperty( prop_name):
        prop = accumWS.run().getProperty( prop_name)
        return prop.value
    else:
        # HACK: should we throw an exception in this case?
        return -1

# -----------------------------------------------------------    
# -----------------------------------------------------------

def register_pvs():
    '''
    Called by the main plugin loader.  This function sets up the mappings
    between process variable names and the callables that calculate their
    values.
    '''
        
    pv_functions_chunk = {}
    pv_functions_post = {}
    
    pv_functions_chunk[r'^PROTONCHARGE$'] = calc_protoncharge    
    pv_functions_chunk[r'^RUNNUM$'] = calc_runnum
    pv_functions_chunk[r'^EVTCNT$'] = calc_evtcnt
    pv_functions_post[r'^EVTCNT_POST$'] = calc_evtcnt_post
    
    # should match M1CNT, M2CNT...M99CNT...M1001CNT, etc..
    pv_functions_chunk[r'^M[0-9]+CNT$'] = calc_beam_mon_cnt()  # note that this is an instance of the class

    # should match M1CNT, M2CNT_POST...M99CNT_POST...M1001CNT_POST, etc..
    pv_functions_post[r'^M[0-9]+CNT_POST$'] = calc_beam_mon_cnt_post
    
    return (pv_functions_chunk, pv_functions_post)
    
    
