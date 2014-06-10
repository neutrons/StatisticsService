#!/usr/bin/env python

########### SVN repository information ###################
# $Date$
# $Author$
# $Revision$
# $URL$
# $Id$
########### SVN repository information ###################

'''
PyEpics widgets for PySide GUI tools

Copyright (c) 2009 - 2012, UChicago Argonne, LLC.
See LICENSE file for details.
'''


__version__ = '0.1'


import epics
import sys              #@UnusedImport
from PySide import QtGui
import pprint           #@UnusedImport

from tools import CaQSignalDef, enum

class CaQLabel(QtGui.QLabel):
    '''
    Provide the value of an EPICS PV on a PySide.QtGui.QLabel
    '''
    # TODO: need to superclass a lot of this

    def __init__(self):
        '''
        :param str text: initial Label text (really, we can ignore this)
        '''
        self.text = ' '*4
        QtGui.QLabel.__init__(self, self.text)

        # define the signals we'll use in the camonitor handler to update the GUI
        self.labelSignal = CaQSignalDef()
        self.labelSignal.newBgColor.connect(self.SetBackgroundColor)
        self.labelSignal.newText.connect(self.SetText)
        
        self.states = enum('DISCONNECTED', 'CONNECTED', 'ALARM')
        self.clut = {   # clut: Color LookUp Table
            self.states.DISCONNECTED:     "#ffffff",      # white
            self.states.CONNECTED:        "#e0e0e0",      # a bit darker than default #f0f0f0
            self.states.ALARM:            "#ff0000",      # red
        }

        self.pv = None
        self.ca_callback = None
        self.ca_connect_callback = None
        self.state = self.states.DISCONNECTED
        self.SetBackgroundColor()

    def connect(self, pvname, ca_callback = None, ca_connect_callback = None):
        '''
        Connect this label with the EPICS pvname
        
        :param str pvname: EPICS Process Variable name
        :param obj ca_callback: EPICS CA callback handler method
        :param obj ca_connect_callback: EPICS CA connection state callback handler method
        '''
        if self.pv is not None:
            self.disconnect()
        if len(pvname) > 0:
            self.ca_callback = ca_callback
            self.ca_connect_callback = ca_connect_callback
            self.pv = epics.PV(pvname, 
                               callback=self.onPVChange,
                               connection_callback=self.onPVConnect)
            self.pv.get_ctrlvars()
            self.state = self.states.CONNECTED
            self.setToolTip(pvname)
    
    def disconnect(self):
        '''
        disconnect from this EPICS PV, if connected
        '''
        if self.pv is not None:
            self.pv.remove_callback()
            pvname = self.pv.pvname
            self.pv.disconnect()
            self.pv = None
            self.ca_callback = None
            self.ca_connect_callback = None
            self.state = self.states.DISCONNECTED
            self.text = ''
            self.SetText()
            self.SetBackgroundColor()
            self.setToolTip(pvname + ' not connected')

    def onPVConnect(self, *args, **kw):
        '''
        respond to a PyEpics CA connection event
        '''
        conn = kw['conn']
        self.text = {      # adjust the text
                          False: '',    #'disconnected',
                          True:  'connected',
                      }[conn]
        self.labelSignal.newText.emit()      # threadsafe update of the widget
        self.state = {      # adjust the state
                          False: self.states.DISCONNECTED,
                          True:  self.states.CONNECTED,
                      }[conn]
        self.labelSignal.newBgColor.emit()   # threadsafe update of the widget
        if self.ca_connect_callback is not None:
            # caller wants to be notified of this camonitor event
            self.ca_connect_callback(**kw)

    def onPVChange(self, pvname=None, char_value=None, **kw):
        '''
        respond to a PyEpics camonitor() event
        '''
        self.text = char_value
        self.labelSignal.newText.emit()      # threadsafe update of the widget
        if self.ca_callback is not None:
            # caller wants to be notified of this camonitor event
            self.ca_callback(pvname=pvname, char_value=char_value, **kw)

    def SetText(self, *args, **kw):
        '''set the text of the Label'''
        self.setText(self.text)

    def SetBackgroundColor(self, *args, **kw):
        '''set the background color of the Label via its stylesheet'''
        color = self.clut[self.state]
        bgStyle = "QFrame {background-color: %s}" % color
        self.setStyleSheet(bgStyle)


#------------------------------------------------------------------


class DemoView(QtGui.QWidget):
    '''
    Show an EPICS PV connection.
    Allow it to connect and disconnect.
    This is a variation of EPICS PV Probe.
    '''

    def __init__(self, parent=None, pvname=''):
        QtGui.QWidget.__init__(self, parent)
        self.value  = CaQLabel()

        grid = QtGui.QGridLayout()
        grid.addWidget(self.value,   0,0)
        self.setLayout(grid)

        self.sig = CaQSignalDef()
        self.sig.newBgColor.connect(self.SetBackgroundColor)
        self.toggle = False

        self.setWindowTitle("Demo CaQLabel")
        if len(pvname)>0:
            self.connect(pvname)

    def connect(self, pvname):
        self.value.connect(pvname, ca_callback=self.callback)

    def callback(self, *args, **kw):
        self.sig.newBgColor.emit()   # threadsafe update of the widget

    def SetBackgroundColor(self, *args, **kw):
        '''toggle the background color of self.value via its stylesheet'''
        self.toggle = not self.toggle
        color = {
                    False: "#ccc333",
                    True:  "#cccccc",
                 }[self.toggle]
        bgStyle = "QFrame {background-color: %s}" % color
        self.value.setStyleSheet(bgStyle)

    
    
#------------------------------------------------------------------


if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    _demo = DemoView(pvname='prj:datetime')
    _demo.show()
    sys.exit(app.exec_())
