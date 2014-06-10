'''
Created on Jun 6, 2014

@author: xmr


Utility functions for generating the config files required by
the EPICS softIoc binary
'''


def generateDbFile( fname, pv_names):
    '''
    Create the .db file that defines all the process variables the softIoc
    binary will manage.
    
    fname is the full pathname to the file to be created.  If it already
      exists, it will be overwritten.
    pv_names is a list of the process variable names
    '''
    
    dbfile = open( fname, 'w')
    # ToDo:  Add a few lines of comments saying the file is auto-generated
    # and include a date and maybe some other stuff.  Need to figure out
    # what constitutes a comment in that file, first.
    for n in pv_names:
        _writeRecord( dbfile, n)
    dbfile.close()


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




def _writeRecord( dbfile, pv_name):
    '''
    Outputs a single 'record' block to the .db file

    dbfile is the file object we're writing to
    pv_name is the name part of the process variable string
    '''
    # Note: For now I just need one of these functions.  Once I figure out
    # what some of the 'field' lines actually do, I might need multiple
    # specialized functions (ie: _writeFloatRecord, _writeIntRecord).
    # We'll have to see how all this shakes out...
    
    dbfile.write( 'record( ao, "$(PREFIX):%s"){\n' % pv_name)
    dbfile.write( '  field(DTYP,"Soft Channel")\n')
    dbfile.write( '  field(VAL,0)\n')
    dbfile.write( '  field(UDF,1)\n')
    dbfile.write( '}\n')