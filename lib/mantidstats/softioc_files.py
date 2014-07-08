'''
Created on Jun 6, 2014

@author: xmr


Utility functions for generating the config files required by
the EPICS softIoc binary
'''


def generateCmdFile( fname, db_fname, prefix):
    '''
    Generates the .cmd file that's passed to the softIoc binary
    
    fname is the full pathname to the file to be created.  If it already
      exists, it will be overwritten.
    db_fname is the full pathname to the (previously generated) .db file.
    prefix is the first part of the process variable names (ie: BL9:CS).  Note:
      there should be no trailing colon on the prefix.
    '''
    
    # Note: For now, we're hard-coding the architecture and the IOC name.
    # In the future, we might want to make these adjustable (or maybe
    # auto-detect the arch...)
    cmdfile = open( fname, 'w')
    cmdfile.write('epicsEnvSet("ARCH","linux-x86_64")\n')
    cmdfile.write('epicsEnvSet("IOC","mantidstatsIOC")\n')
    cmdfile.write('dbLoadRecords("%s","PREFIX=%s")\n'%(db_fname, prefix))
    cmdfile.write('iocInit\n')
    cmdfile.close()



# These are helpers that the various plugin modules can use to generate
# the .db records for the PV's they output.  I expect these will grow
# more numerous and complex as I figure out what the various fields are
# useful for.

def writeStandardAORecord( pv_name):
    '''
    Returns a string containing a single 'record' block of type 'ao' (analog
    output).

    pv_name is the name part of the process variable string.
    '''
    record = 'record( ao, "$(PREFIX):%s"){\n' % pv_name
    record += '  field(DTYP,"Soft Channel")\n'
    record += '  field(SCAN,"Passive")\n'
    record += '  field(VAL,0)\n'
    record += '  field(UDF,1)\n'
    record += '}\n'
    record += '\n'
    return record

def writeStandardWaveformRecord( pv_name, num_elements):
    '''
    Returns a single 'record' block of type 'waveform'

    pv_name is the name part of the process variable string
    num_elements is the number of individual values in the waveform
    '''
    record = 'record( waveform, "$(PREFIX):%s"){\n' % pv_name
    record += '  field(DTYP,"Soft Channel")\n'
    record += '  field(SCAN,"Passive")\n'
    record += '  field(FTVL,"LONG")\n'
    record += '  field(NELM,"%d")\n'%num_elements
    record += '  field(UDF,1)\n'
    record += '}\n'
    return record

