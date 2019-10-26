#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -*- python -*- 



from pydbus import SessionBus

#get the session bus
bus = SessionBus()
#get the object
the_object = bus.get("net.syuppod.Test")

#call the methods and print the results
#reply = the_object.Hello()
#print(reply)

#help(bus.request_name)

reply = the_object.publish_branch_old_local()
print(reply)

#the_object.Quit()
