Instructions
============

Needs to be fleshed out. Will take from Etan's instructions and add our own.

Container Routing Setup
-----------------------

The routing policy database (RPDB) allows for routing decisions to be made based on factors other than destination address. The database checks these extra factors to decide which routing table to use. A rule with priority 0 (highest priority), matching all traffic, to check the "local" routing table first, is the only fixed unchangable rule in the database. Our problem with the "local" routing table is that it sends all traffic with a destination IP of the host, to the host. Here's how we change that:

First, create a new routing table called "local_copy", with a table number of 252::
        
    echo "252    local_copy" >> /etc/iproute2/rt_tables

Copy the local table over to local_copy::
    
    ip route show table local | while read ROUTE ; do
    ip route add table local_copy $ROUTE
    done

Flush the local table, so that the RPDB moves on after finding it empty::

    ip route flush table local

Add a rule to the RPDB to check the local_copy only when receiving packets from eth0::

    ip rule add iif eth0 lookup local_copy priority 1

Make sure to install a default route in the container's routing table::

    ip route add default via <default gateway>

Amazon AWS
----------
NAT rules



Docker, OVS installation
------------------------
