# -*- coding: utf-8 -*-
# -*- python3 -*- 
# Copyright Jérôme Venturi: jerome dot Venturi at gmail dot com
# Distributed under the terms of the GNU General Public License v3

# TODO other attributes and many more :)

def git_available_version(myobject, opt, machine):
    """Display available git kernel or branch version, if any"""
    # TODO give choice to print all the version or just n version with (+the_number_which_rest)
    #      ex: 
    switch = {
        'branch'    :   {
                    'caller'    :   'get_branch_attributes',
                    'msg'       :   _('Available git branch version:'),
                    'none'      :   _('not available')
                    },
        'kernel'    :   {
                    'caller'    :   'get_kernel_attributes',
                    'msg'       :   _('Available git kernel version:'),
                    'none'      :   _('not available')
                    }
        }
    reply = getattr(myobject, switch[opt]['caller'])('available', 'all')
    if reply == 'disable':
        print('Error: git implantation is disable')
        return
    elif reply == '0.0' or reply == '0.0.0':
        msg = switch[opt]['none']
    else:
        version_list = reply.split(' ')
        msg_len = len(version_list)
        if msg_len > 1:
            msg = version_list[-1] + ' (+' + str(msg_len - 1) + ')'
        else:
            msg = version_list[0]
    
    if not machine:
        print('[*] {0}'.format(_(switch[opt]['msg'])))
        print(f'    - {msg}')
    else:
        print(msg)
