'''
Created on Jul 2, 2014

@author: xmr

Used to test the EVT_HISTO process variables - reads the data and converts it to an image file
'''

from epics import PV
import numpy as np
from PIL import Image  # @UnresolvedImport
import math

# Some constants we'll need
# (Make sure these stay up-to-date with the main program!)
ARRAY_WIDTH = 610
ARRAY_HEIGHT = 800

PV_NAME = "BL9_TEST:CS:EVTHISTO"
#PV_NAME = "BL9:CS:EVTHISTO"
        

# some globals that may be useful for mapping the colors
max_val = 0
half_max_val = 0
log_max = 0
half_log_max = 0
one_third_log_max = 0
two_thirds_log_max = 0

def main():
    global max_val, half_max_val, log_max, half_log_max, one_third_log_max, two_thirds_log_max
    
    histo = PV(PV_NAME)
    
    # Fetch the data from the PV and convert it back to a
    # 2D array with the proper dimensions 
    data = np.array(histo.value)
    data = data.reshape(ARRAY_WIDTH, ARRAY_HEIGHT)

    max_val = data.max()  # used to scale the color mapping
    print "Max value:", max_val
    half_max_val = max_val / 2
    # MantidPlot defaults to a logarithmic scale, so we will, too
    log_max = math.log(max_val,10)
    half_log_max = log_max / 2
    one_third_log_max = log_max / 3
    two_thirds_log_max = one_third_log_max * 2
         
    img = Image.new("RGB", (ARRAY_WIDTH, ARRAY_HEIGHT))

    # Write the individual image pixels based on the array data
    # -1 will be converted to black, all other values will range
    # from blue to purple
    for x in range(ARRAY_WIDTH):
        for y in range(ARRAY_HEIGHT):
            evt_cnt = data[x,y]
            if evt_cnt == -1:
                img.putpixel( (x,y), (0,0,0)) # write a black pixel
            elif evt_cnt == 0:
                img.putpixel( (x,y), (0,0,255))
            else:
                img.putpixel( (x,y), map_color_3(evt_cnt))
                
            # Note: putpixel() is known to be slow, but there doesn't seem to
            # be a better way to do things.
    
    img.show()  # show() is slow and klunky and requires 'xv' - it's really
                # meant only for debugging.



# returns an R,G,B tuple
def map_color_1( evt_cnt):
    rv = (0,0,0)  
    if evt_cnt < half_max_val:
        color = int((math.log(evt_cnt,10) / half_log_max) * 255)
        rv = (color, 0, 255)
    else:
        color = int(( (math.log(evt_cnt - half_max_val,10) / half_log_max) * 255))
        rv = (255-color, color, 255)
    
    return rv

# Another method for mapping event counts to colors
# returns an R,G,B tuple
def map_color_2( evt_cnt):
    color16 = int((math.log(evt_cnt,10) / log_max) * 65535)
    red_channel = color16 >> 8
    green_channel = color16 & 0xFF
    return (red_channel, green_channel, 255)


def map_color_3( evt_cnt):
    rv = (0,0,0)  
    log_evt_cnt = math.log(evt_cnt, 10)
    if log_evt_cnt < one_third_log_max:
        color = int((log_evt_cnt / one_third_log_max) * 255)
        rv = (color, 0, 255)
    elif log_evt_cnt < two_thirds_log_max:
        color = int(( (log_evt_cnt - one_third_log_max) / one_third_log_max) * 255)
        rv = (255-color, color, 255-color)
    else:
        color = int(( (log_evt_cnt - two_thirds_log_max) / one_third_log_max) * 255)
        rv = (color, 255, color)
        #print "Events:  %d ==> %s"%(evt_cnt, str(rv))
    
    return rv

if __name__ == '__main__':
    main()
