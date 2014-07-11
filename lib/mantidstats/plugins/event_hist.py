'''
Created on Jun 17, 2014

@author: xmr

Holds calculation function for the event histogram PV
'''

import numpy as np

import logging
#import logging.handlers
import math

from softioc_files import writeStandardWaveformRecord
# -----------------------------------------------------------------------------


'''
Some notes about CORELLI geometry:

A "16Pack" is .20955 m in X and .835921875 m in Y.
It is 16 Pixels across and 256 (in the case of CORELLI) down.
That means each pixel is  0.013096875 m  wide and 0.00326531982422 m tall.

Min Y value is (probably) -1.223.  Max is (probably) 1.38475. (Will have to
verify this with actual data once we actually have code to test with)

Total height: 2.60775
Actual vertical 'pixel space' (allowing for spaces between the detector
packs): 798.6 (round up to 800)


(Covers about 180 degrees) The Y axis is flat.  The X & Z coordinates must be
used to "unwrap" the cylinder into a flat surface.  Since we're only worried
about getting the pixels correct relative to each other, can probably use
the angle off the X (or Z axis)

Each "16Pack" is flat, but they're arranged in a section of a cylinder around
the Y axis.  Thus, Y values (in meters) for each pixel should map pretty much
directly to the Y value in the output array.  To map the X value of the output
array, we'll calculate the angle off the Z axis on the X-Z plane
(arctan (X/Z)).
'''


class GeometryError(Exception):
    '''
    An exception that is thrown if the instrument geometry doesn't match
    what we were expecting.
    '''
    pass


class calc_evthisto:
    '''
    Calculates the EVTHISTO process variable.
    '''
    # Note: We're operating on the chunkWS, which means we need to keep a
    # running sum of the events for each pixel in a static variable and add
    # the events in chunkWS to it.  (And reset all the elements to 0 when the
    # run # changes.)
                   
    def __init__(self):
       
        # create all the attributes that the __call__() function is going to
        # need
        self._last_run_num = -1
              
        # Geometry constants - we need to verify these are still true
        # before we do much else.  (If they're not true, it probably
        # means somebody messed with the instrument definition file.)
        # See _finish_init()
        self._NUM_PIXELS = 372736
        self._MIN_THETA = -0.424492
        self._MAX_THETA = 2.652780
        self._MIN_Y = -1.222825
        self._MAX_Y = 1.384750
        self._AVERAGE_RADIUS = 2.590189
        
        self._PIXEL_ANGLE = 5.056296e-3 # horizontal angle, in radians
        self._PIXEL_HEIGHT = 3.26531982422e-3 # vertical size, in meters
        
        # The actual dimensions of the array data we'll output
        self._OUTPUT_ARRAY_WIDTH = 610
        self._OUTPUT_ARRAY_HEIGHT = 800
        
        
        # Need to keep track of the run numbers so we can reset the output
        # at run transitions
        self._run_num = -99
        
        # there isn't too much we can do until we actually have a workspace
        # to work with, so just set a boolean.  We'll test it down in
        # __call__() and complete the initialization then.
        self._is_init = False
        
        # maps pixel ID's to their <x,y> coordinates in the output array
        self._pixel_id_map = { }
        
        # holds the actual histogram data
        self._output = np.empty((self._OUTPUT_ARRAY_WIDTH,
                                 self._OUTPUT_ARRAY_HEIGHT), int)
        self._reset()

        
    def __call__( self, chunkWS, pv_name, run_num, **kwargs):
        '''
        Process the chunk workspace and update the histogram array with
        any new events
        '''
        
        logger = logging.getLogger(__name__)
        logger.debug( "Inside __call__")
        
        if not self._is_init:
            self._finish_init( chunkWS)
        
        # Zero the entries in the output array when the run number changes    
        if self._run_num != run_num:
            self._reset()
            self._run_num = run_num
        
        # This serves as both a sanity check and (in the case of 0 events)
        # a means of skipping a bunch of unnecessary work.
        total_event_count = chunkWS.getNumberEvents()
        
        if total_event_count > 0:
            running_event_count = 0
            
            # loop through all the spectra in the workspace
            num_spectra = chunkWS.getNumberHistograms()
            for i in range(num_spectra):
                num_events = chunkWS.getEventList(i).getNumberEvents()
                if num_events > 0:
                    try:
                        (x,y) = self._pixel_id_map[i]
                        #logger.debug( "Spectrum %d maps to %d,%d" % (i, x, y))
                        #logger.debug( "Old value at %d,%d: %d" % (x, y, self._output[x,y]))
                        self._output[x,y] += num_events
                        #logger.debug( "New value at %d,%d: %d" % (x, y, self._output[x,y]))
                        running_event_count += num_events
                    except KeyError:
                        logger.error( "Spectrum #%d wasn't in the pixel map!"%i)
                
            # end of for loop
            if running_event_count != total_event_count:
                logger.error( "Running event count (%d) doesn't match the "
                              "workspace total event count (%d)!" % 
                              (running_event_count, total_event_count))
        else:
            logger.debug( "0 events in this chunk workspace")
            
            
        logger.debug("About to return from __call__")
        # This looks a little strange, but it works.  'flat' is an iterator
        # over the entire array and the value attribute on PV's (which this
        # is passed directly to) wants a sequence (when the PV type is
        # a waveform)
        return self._output.flat

    
    def _finish_init( self, chunkWS):
        '''
        Complete all the initialization steps that had to be deferred until
        we had an actual workspace.
        '''            
        # We need to map detector ID's to a set of <X,Y> coordinates.  Since
        # the detectors basically form a cylinder wrapped around the Y axis,
        # we'll essentially 'unroll' them.
        #
        # A "16Pack" is .20955 m in X and .835921875 m in Y.
        # It is 16 Pixels across and 256 (in the case of CORELLI) down.
        # That means each pixel is  0.013096875 m  wide and 0.00326531982422 m
        # tall.  On average, each pixel is also ~ 2.590189 m (though this
        # varies between 2.4 & 2.8 m) from the origin, which means it occupies
        # ~5.056296e-3 radians in the horizontal plane.
        # 
        # The pixels should mostly be in nice, neat rows, so we can just use
        # their Y values (in meters) to map the the Y coordinate of our
        # output array.  Since the columns aren't so neat, we'll use the
        # angle relative to the Z axis (ignoring the Y value and just
        # concentrating on 2D space) to map pixels into appropriate spots in
        # the output array.  I'm calling this angle theta.
        # TODO: Verify that the 'theta' I see references to in the source
        # code means the same thing.
        #
        # The min and max theta values are: -0.424492 & 2.652780 radians
        # Given that each pixel is 5.056296e-3 radians wide, the horizontal size
        # of our output array is: 608.6 (We'll round up to 610.) 
        #
        # The min and max Y values (in meters) are: -1.222825 & 1.384750
        # Given that each pixel is 0.00326531982422  m tall, the vertical size
        # of our output array is: 798.6  (We'll round up to 800.)
        #
        # The coordinate system we use in the output array will put 0,0 at
        # the top, left corner and 609,799 at the bottom, right corner.
        # Because of the coordinate system in use at the beamline, this
        # means that 0,0 in the output array will correspond to 
        # MAX_THETA,MAX_Y and and 610,800 will be MIN_THETA,MIN_Y. 
        
                
        logger = logging.getLogger(__name__)
        logger.debug( "Inside _finish_init()")
        
        self._validate_geometry(chunkWS)
        
        ins = chunkWS.getInstrument()
        num_spectra = chunkWS.getNumberHistograms() 
        logger.debug( "Num spectra: %d"%num_spectra)
        
        # A couple of constants that get used repeatedly down below.
        # Calculated once here to save time
        total_height = self._MAX_Y - self._MIN_Y
        total_angle = self._MAX_THETA - self._MIN_THETA
        
        logger.debug( "Creating detector ID to output coordinate map")
        for ws_index in range( num_spectra):
            det = ins.getDetector( ws_index)
            if (ws_index != det.getID()):
                logger.error( "Detector ID / workspace index mismatch: "
                                "%d != %d"%(ws_index, det.getID()))
                # EventWorkspace docs say the workspace index and detector ID
                # should always be equal, so we won't look at the detector ID
                # except in this one check
                
            pos = det.getPos()
            theta = self._compute_theta( pos.getX(), pos.getZ())
            y = pos.getY()
            outX = int(((self._MAX_THETA - theta) / total_angle) * self._OUTPUT_ARRAY_WIDTH - 1)          
            outY = int(((self._MAX_Y - y) / total_height) * self._OUTPUT_ARRAY_HEIGHT - 1)
            
            self._pixel_id_map[ws_index] = (outX, outY);  
        
        # Now, check for cases where 2 pixels map to the same output location...
        logger.debug( "Checking for duplicates in detector ID to output coordinate map")
        locations = self._pixel_id_map.values()
        locations.sort()
        for n in range(len(locations) - 1):
            if locations[n] == locations[n+1]:
                logger.error( "Duplicate mapping into output array at %d,%d"%(locations[n][0], locations[n][1]))
                #TODO: now what do we do?
        
        logger.debug("Duplicate checks complete.")        
                
        self._reset() # set the initial value for the output array
        self._is_init = True
        

    def _reset( self):
        '''
        Reset the histogram array.
        
        Note: -1 means 'no detector here' and 0 means 'no events for
        this detector'
        '''
        self._output.fill(-1)
        
        # Every location that actually has a detector is set to 0
        for n in self._pixel_id_map.values():
            self._output[n[0], n[1]] = 0
            
        # Note: it would probably be faster to fill with 0 and then individually
        # set 'no detector' positions to -1, except that I don't have a list of
        # of locations that *don't* have detectors.  I could make one, but it's
        # probably not worth the cost in memory usage
        
        

    def _validate_geometry(self, chunkWS):
        '''
        Compute various values for the geometry of the instrument and verify
        that they match what we're expecting.
        
        Note: The function returns no value.  If it detects a problem with
        the geometry, it throws an exception.
        '''
        
        logger = logging.getLogger(__name__)
        logger.debug( "Validating instrument geometry")
        
        ins = chunkWS.getInstrument()
        num_spectra = chunkWS.getNumberHistograms()

        if (num_spectra != self._NUM_PIXELS):
            raise GeometryError( "Pixel count is wrong.  Expected %d, but "
                                 "actual value is %d"%(self._NUM_PIXELS,
                                                       chunkWS.getNumberHistograms()))
        
        min_theta = 999999.0
        max_theta = -9999999.0       
        min_y = 9999999.0
        max_y = -9999999.0
        min_radius = 99999.0
        max_radius = -99999.0
        radius_sum = 0  # for computing the average radius
        
        for ws_index in range( num_spectra):
            det = ins.getDetector( ws_index)
                
            # Strictly speaking, we should use a second 'if' clause instead of
            # an 'elif' in the tests below as it could cause an error in one
            # particular case: if the actual maximum value happens to be the
            # first value tested, it will probably still be less than the
            # initial min value set above, so we will set min_<whatever> and
            # then skip the test for max_<whatever>.
            #
            # Using 'else if' speeds things up noticeably, though, so I'm using
            # it anyway.  
            pos = det.getPos()
            temp = pos.getY()
            if (temp < min_y):
                min_y = temp
            elif (temp > max_y):
                max_y = temp
                
            temp = self._compute_theta( pos.getX(), pos.getZ())
            if (temp < min_theta):
                min_theta = temp
            elif (temp > max_theta):
                max_theta = temp
                
            temp = self._compute_radius( pos.getX(), pos.getY(), pos.getZ())
            if (temp < min_radius):
                min_radius = temp
            elif (temp > max_radius):
                max_radius = temp
                
            radius_sum += temp
            
        
        if not self._approx_equal(min_theta, self._MIN_THETA, 6):
            raise GeometryError( "Unexpected minimum theta value. Expected "
                                 "%f, but actual value is %f"%
                                 (self._MIN_THETA, min_theta))
            
        if not self._approx_equal(max_theta, self._MAX_THETA, 6):
            raise GeometryError( "Unexpected maximum theta value. Expected "
                                 "%f, but actual value is %f"%
                                 (self._MAX_THETA, max_theta))
            
        if not self._approx_equal(min_y, self._MIN_Y, 6):
            raise GeometryError( "Unexpected minimum Y value. Expected "
                                 "%f, but actual value is %f"%
                                 (self._MIN_Y, min_y))
        
        if not self._approx_equal(max_y, self._MAX_Y, 6):
            raise GeometryError( "Unexpected maximum Y value. Expected "
                                 "%f, but actual value is %f"%
                                 (self._MAX_Y, max_y))

        avg_radius = radius_sum / num_spectra
        if not self._approx_equal(avg_radius, self._AVERAGE_RADIUS, 6):
            raise GeometryError( "Unexpected average radius value. Expected "
                                 "%f, but actual value is %f"%
                                 (self._AVERAGE_RADIUS, avg_radius))
            
        logger.debug( "Instrument geometry validated.")
        
                
    def _compute_theta(self, x, z):
        # todo - probably don't need a separate function for this...
        return math.atan2( x, z)  # arctan of x/z
    
    def _compute_radius(self, x, y, z):
        return math.sqrt((x*x) + (y*y) + (z*z))
    
    def _approx_equal(self, a, b, sigfig):
        return abs(a-b) < (1.0 / math.pow(10, sigfig))        

# End of class calc_evthisto      
   
# -----------------------------------------------------------    

# This module only calculates a single PV, so the function to create the
# EPICS db record is pretty simple
def generateDbRecord( pv_name, **kwargs):
    '''
    Returns a string defining the database record for the specified pv_name
    
    Called by the main program when it needs to generate the config files
    for the softIOC program.
    '''
    ce = calc_evthisto()
    return writeStandardWaveformRecord( pv_name, (ce._OUTPUT_ARRAY_WIDTH * ce._OUTPUT_ARRAY_HEIGHT) )
        
def register_pvs():
    '''
    Called by the main plugin loader.  This function sets up the mappings
    between the (only) process variable name and the callable that calculates
    it's value.
    '''
        
    pv_functions_chunk = {}
    pv_functions_dbrecord = {}

    # Match 'EVTHISTO' exactly    
    pv_functions_chunk[r'^EVTHISTO$'] = calc_evthisto() # pass back an instance of the class
    pv_functions_dbrecord[r'^EVTHISTO$'] = generateDbRecord
    
    # Note: No post processing, so returning an empty dict
    return (pv_functions_chunk, {}, pv_functions_dbrecord)
