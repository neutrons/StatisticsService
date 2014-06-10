#!/usr/bin/env python

########### SVN repository information ###################
# $Date$
# $Author$
# $Revision$
# $URL$
# $Id$
########### SVN repository information ###################

'''
demo view for EPICS PV connection class: pv.PvConnection()

Copyright (c) 2009 - 2012, UChicago Argonne, LLC.
See LICENSE file for details.
'''


# - - - - - - - - - - - - - - - - - - Imports


import sys
from PySide import QtGui
from caqlabel import CaQLabel
from tools import CaQSignalDef


# - - - - - - - - - - - - - - - - - - Global


__svnid__ = "$Id$"


# - - - - - - - - - - - - - - - - - - classes


class DemoView(QtGui.QWidget):
    '''
    Show an EPICS PV connection.
    Allow it to connect and disconnect.
    This is a variation of EPICS PV Probe.
    '''

    def __init__(self, parent=None, pvname=''):
        QtGui.QWidget.__init__(self, parent)

        name_label  = QtGui.QLabel("PV Name:")
        self.pvname = QtGui.QLineEdit(pvname)
        self.pvname.returnPressed.connect(self.onPVNameReturn)
        #self.pvname.editingFinished.connect(self.onPVNameReturn)
        value_label = QtGui.QLabel("PV Value:")
        self.value  = CaQLabel()  
        
        status_label  = QtGui.QLabel("status:")
        self.status  = QtGui.QLabel("just starting")
        self.status_text = ''
        
        content_label  = QtGui.QLabel("content:")
        self.content  = QtGui.QLabel("just starting")
        self.content_text = ''

        self.sig_status = CaQSignalDef()
        self.sig_status.newText.connect(self.SetStatus)
        self.sig_content = CaQSignalDef()
        self.sig_content.newText.connect(self.SetContent)

        grid = QtGui.QGridLayout()
        grid.addWidget(name_label,    0, 0)
        grid.addWidget(self.pvname,   0, 1)
        grid.addWidget(value_label,   1, 0)
        grid.addWidget(self.value,    1, 1)
        grid.addWidget(status_label,  2, 0)
        grid.addWidget(self.status,   2, 1)
        grid.addWidget(content_label, 3, 0)
        grid.addWidget(self.content,  3, 1)

        self.setLayout(grid)
        self.setWindowTitle("Demo PV object")
        if len(pvname)>0:
            self.onPVNameReturn()

    def onPVNameReturn(self, *args, **kw):
        self.value.connect(self.pvname.text(), 
                           ca_callback=self.pv_update, 
                           ca_connect_callback=self.connect_update)
    
    def connect_update(self, **kw):
        self.status_text = {True: 'connected', False: 'disconnected'}[ kw['conn'] ]
        self.sig_status.newText.emit()
    
    def pv_update(self, **kw):
        print 'pv_update!! ', kw
        self.content_text = "updated:" + str(kw['timestamp'])
        self.sig_content.newText.emit()
    
    def SetStatus(self, *args, **kw):
        self.status.setText(self.status_text)
    
    def SetContent(self, *args, **kw):
        self.content.setText(self.content_text)


# - - - - - - - - - - - - - - - - - - methods


# - - - - - - - - - - - - - - - - - - main


if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    pvname = 'prj:datetime'
    if len(sys.argv) > 1:
        pvname = sys.argv[1]
    probe = DemoView(pvname=pvname)
    probe.show()
    sys.exit(app.exec_())
