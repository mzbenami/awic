Instructions
============

Needs to be fleshed out. Will take from Etan's instructions and add our own.


Host Routing Configuration
==========================

Add a route to the host machine for the container subnet::

	sudo route add -net <container subnet>/<mask> <next-hop carrier interface>


Carrier Configuration
=====================
Software:

Ubuntu 13.10 (64-bit)
Docker, 0.8.1
Open vSwitch, 1.10.2

Docker installation instructions: https://docs.docker.com/installation/ubuntulinux/#ubuntu-raring-1304-and-saucy-1310-64-bit

Docker Patching
---------------

Getting lxc source and untarring it::

    apt-get source lxc
    cd lxc-1.0.0~alpha1/ (path to ``apt-get source`` output)

Moving and applying patch (orginal article: http://voices.canonical.com/zhengpeng.hou/lxc-and-openvswtich/)::

    cp <path_to_project>/lxc-vswitch.patch ./
    git apply lxc-vswitch.patch

Configuring::

    ./configure --enable-apparmor

If you are missing libcap or the apparmor development tools, run::

    sudo apt-get install libcap-dev
    sudo apt-get install libapparmor-dev

Build and install::

    make
    sudo make install


Open vSwitch Configuration
----------------------------
Adding OVS bridge::

    sudo ovs-vsctl add-br <bridge name>

When a bridge is added a virtual interface on the host is automatically created and attached to the bridge.

To connect a real interface (eth0) to the bridge (Phase 1 deployment)::
	
	sudo ovs-vsctl add-port <bridge name> eth0

In a Phase 1 deployment, eth0 does not have an IP address, and the virtual interface created when the open vSwitch is created should be assigned an IP address on the same subnet as the "host-only" interface on the host. Remove the IP address from eth0::
	
	sudo ifconfig eth0 0

In a Phase 2 deployment, eth0 keeps it's IP address. The virtual interface created by OVS should be assigned an IP address in the subnet of the containers.

Associate Docker with OVS::
	
	sudo service docker stop    		-- (kills any running instance of docker)
	docker -d -b <OVS bridge name> &	-- (runs docker in daemon mode)

Start new one on ovs bridge::

    sudo dhclient -1 -v obr-dock

Setup proper netmask on host::

    sudo route -n add -net 172.16.0.0/16 -interface vmnet8 (virtual interface on host)


Container Configuration on Carrier VM
-------------------------------------

Create a container::

	docker run -privileged ubuntu /bin/bash

See a list of active containers::
	
	docker ps

Attach to a container::

	docker attach <container name>
	

Container Routing Setup
=======================

Insider the container.
Assign an IP address to the containers eth0::
	
	ifconfig eth0 <address>/<mask>

We want to allow packets originating from the container to hit "the wire" even if the destination IP is on the container. The routing policy database (RPDB) allows for routing decisions to be made based on factors other than destination address. The database checks these extra factors to decide which routing table to use. A rule with priority 0 (highest priority), matching all traffic, to check the "local" routing table first, is the only fixed unchangable rule in the database. Our problem with the "local" routing table is that it sends all traffic with a destination IP of the host, to the host. Here's how we change that:

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

IP Forwarding (transit routing) should be disabled::

	echo '0' > /proc/sys/net/ipv4/ip_forward


Amazon AWS
==========

Configure Management VM
-----------------------



Configure non-gateway carrier VMs
---------------------------------

Configure gateway/carrier VM
-----------------------------








