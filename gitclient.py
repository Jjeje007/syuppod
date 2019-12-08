# -*- coding: utf-8 -*-
# -*- python3 -*- 
# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3



def _check_enable(myobject):
    """Check if git implantation is enable"""
    # This has to be call every time we need to access
    # method from Git bus object - to make sure it's enable
    reply = myobject.get_set_enable('get')
    if reply == 'True':
        return True
    else:
        return False
