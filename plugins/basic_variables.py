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

# -----------------------------------------------------------------------------

def calc_runnum( chunkWS, **extra_kwargs):
    '''
    Calculates the RUNNUM process variable.
    '''
    
    # This one is about as simple as it gets    
    return chunkWS.getRunNumber()   
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
# ------------------------------------------------


def register_pvs():
    '''
    Called by the main plugin loader.  This function sets up the mappings
    between process variable names and the callables that calculate their
    values.
    '''
        
    pv_functions_chunk = {}
    pv_functions_post = {}
    
    pv_functions_chunk['PROTONCHARGE'] = calc_protoncharge    
    pv_functions_chunk['RUNNUM'] = calc_runnum
    pv_functions_chunk['EVTCNT'] = calc_evtcnt
    pv_functions_post['EVTCNT_POST'] = calc_evtcnt_post
    
    return (pv_functions_chunk, pv_functions_post)
    
    
