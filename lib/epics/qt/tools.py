#!/usr/bin/env python

########### SVN repository information ###################
# $Date$
# $Author$
# $Revision$
# $URL$
# $Id$
########### SVN repository information ###################

'''
tools used in this package

Copyright (c) 2009 - 2012, UChicago Argonne, LLC.
See LICENSE file for details.
'''


# - - - - - - - - - - - - - - - - - - Imports


from PySide import QtCore


# - - - - - - - - - - - - - - - - - - Global


__svnid__ = "$Id$"


# - - - - - - - - - - - - - - - - - - class


class CaQSignalDef(QtCore.QObject):
    '''
    Define the signals used to communicate between the PyEpics
    thread and the PySide (main Qt4 GUI) thread.
    '''
    # see: http://www.pyside.org/docs/pyside/PySide/QtCore/Signal.html
    # see: http://zetcode.com/gui/pysidetutorial/eventsandsignals/
    
    newFgColor = QtCore.Signal()
    newBgColor = QtCore.Signal()
    newText    = QtCore.Signal()


# - - - - - - - - - - - - - - - - - - methods


def enum(*sequential, **named):
    '''
    typesafe enum
    
    EXAMPLE::

        >>> Numbers = enum('ZERO', 'ONE', 'TWO', four='IV')
        >>> Numbers.ZERO
        0
        >>> Numbers.ONE
        1
        >>> Numbers.four
        IV
    
    :see: http://stackoverflow.com/questions/36932/whats-the-best-way-to-implement-an-enum-in-python
    '''
    enums = dict(zip(sequential, range(len(sequential))), **named)
    return type('Enum', (), enums)


def _demo_():
    '''demonstrate use of this module'''
    enums = enum('ZERO', 'ONE', 'TWO', four='IV')
    from pprint import pprint
    pprint(enums)
    print enums.ZERO
    print enums.ONE
    print enums.TWO
    print enums.four


# - - - - - - - - - - - - - - - - - - main


if __name__ == '__main__':
    _demo_()
