from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.util import dpid_to_str
from pox.lib.util import str_to_bool
from pox.lib.addresses import IPAddr, EthAddr
import time
import pox.lib.packet as pkt

log = core.getLogger()

# We don't want to flood immediately when a switch connects.
# Can be overriden on commandline.
_flood_delay = 0

# CONSTANTS, NEED TO BE READ FROM DATABASE
HOST_GATEWAY_IP = '172.16.56.1'
HOST_GATEWAY_NET = '172.16.56.0'
HOST_GATEWAY_MASK = 24
FAKE_ARP_RESPONSE_MAC = 'ab:cd:ef:12:34:45'

# global helper methods
def _dpid_to_mac (dpid):
    return EthAddr("%012x" % (dpid & 0xffFFffFFffFF,))

def isHostAddr(ipaddr):
    return isInHostNetwork(ipaddr) and ipaddr != HOST_GATEWAY_IP

def isInHostNetwork(ipaddr):
    return ipaddr.in_network(HOST_GATEWAY_NET, HOST_GATEWAY_MASK)

def isBroadcastAddr(ipaddr):
    return str(ipaddr).split('.')[3] == '255'

def parseIPAddr(src_dst, packet):
    if src_dst == 'src':
        if packet.type == pkt.ethernet.ARP_TYPE:
            return packet.payload.protosrc
        else:
            return packet.payload.srcip
    
    if packet.type == pkt.ethernet.ARP_TYPE:
        return packet.payload.protodst
    else:
        return packet.payload.dstip

# An instance of this class registers as a listener
# to one or more connections from openflow-enabled switches
class LearningSwitch(object):

    class Entry(object):		
        def __init__ (self, mac=None, port=None):
            self.mac = mac
            self.port = port
	
    class ConnectedSwitch(object):
            
        def __init__ (self, connection, port = of.OFPP_LOCAL):
            self.connection = connection
            self.dpid = connection.dpid
            self.mac = EthAddr(dpid_to_str(self.dpid))
            self.ipaddr = IPAddr(connection.sock.getpeername()[0])
            self.port = port 
		
    def __init__ (self, connection, transparent):
        self.transparent = transparent
        self.switches = {}
        self.macTable = {}
        self.arpTable = {}
        self.addSwitch(connection)
        self.arpTable[(IPAddr('172.16.56.101'), 8000)] = EthAddr('32:af:a4:6d:58:db')
        self.arpTable[(IPAddr('172.16.56.102'), 9000)] = EthAddr('da:07:b8:57:fb:94')
            
    def addSwitch(self, connection):
        connection.addListeners(self)
        switch = self.ConnectedSwitch(connection)
        self.switches[connection.dpid] = switch
        self.arpTable[switch.ipaddr] = self.Entry(switch.mac, switch.port)
    
    def _handle_PacketIn(self, event):

        # generic send, adding flow matching packet to the flow table
        def send(event, packet, outport):
            print "-----------SEND---------------"
            msg = of.ofp_flow_mod()
            msg.data = event.ofp
            msg.match = of.ofp_match.from_packet(packet)
            msg.actions.append(of.ofp_action_output(port = outport))
            print "!!!!!!!SEND_OUTPORT: " + str(outport) 
            event.connection.send(msg)

        # generic flood, no flow is added to the flow table
        def flood(event):
            print "-----------FLOODING----------"
            msg = of.ofp_packet_out()
            msg.data = event.ofp
            msg.actions.append(of.ofp_action_output(port = of.OFPP_FLOOD))

            event.connection.send(msg)

        # flow destined to a host (container), destination mac address is rewritten
        def sendHostFlow(event, packet, mac, port):
            print "------------SEND HOST FLOW------------"
            msg = of.ofp_flow_mod()
            msg.match = of.ofp_match.from_packet(packet)
            msg.data = event.ofp
            msg.actions.append(of.ofp_action_dl_addr.set_dst(mac))
            msg.actions.append(of.ofp_action_output(port = port))
            print "!!!!!!!SEND_HOSTFLOW_OUTPORT: " + str(port)                
            event.connection.send(msg)
        
        # proxy ARP responses using dummy source mac
        def proxyArp(event, packet):
            print "---------PROXY ARP------------------"
            
            a = packet.payload
            
            r = pkt.arp()
            r.hwtype = a.hwtype
            r.prototype = a.prototype
            r.hwlen = a.hwlen
            r.protolen = a.protolen
            r.opcode = pkt.arp.REPLY
            r.hwdst = a.hwsrc
            r.protodst = a.protosrc
            r.protosrc = a.protodst
            r.hwsrc = EthAddr(FAKE_ARP_RESPONSE_MAC)
            e = pkt.ethernet(src = EthAddr(FAKE_ARP_RESPONSE_MAC),
                        dst=a.hwsrc, type = pkt.ethernet.ARP_TYPE)
            e.payload = r
            msg = of.ofp_packet_out()
            msg.data = e.pack()
            msg.actions.append(of.ofp_action_output(port = event.port))
            print "arp reply" + str(e.__dict__) + str(e.next.__dict__)
            print "!!!!!!ARP_REPLY OUTPORT: " + str(event.port)
            event.connection.send(msg)
        
        # drop by having no action set, and adding flow to the table
        # duration (timeout values) for flow are optional
        def drop (event, duration = None):
            """
            Drops this packet and optionally installs a flow to continue
            dropping similar ones for a while
            """
           # if duration is not None:
           #     if not isinstance(duration, tuple):
           #         duration = (duration,duration)
            msg = of.ofp_flow_mod()
            msg.match = of.ofp_match.from_packet(packet)
            #     msg.idle_timeout = duration[0]
            #     msg.hard_timeout = duration[1]
            if event.ofp.buffer_id is not None:
                msg.buffer_id = event.ofp.buffer_id
            event.connection.send(msg)
           # elif event.ofp.buffer_id is not None:
           # msg = of.ofp_packet_out()
           # msg.buffer_id = event.ofp.buffer_id
           # msg.in_port = event.port
           # event.connection.send(msg)

        # packet enters here
        self.lastEventIn = event
        packet = event.parsed
        
        # update the layer 2 learning table
        self.macTable[(event.dpid, packet.src)] = event.port

        # print info about packet to console
        print("handle packet")
        print packet.__dict__
        print "------"
        print packet.payload.__dict__
        print "------"
        print event.__dict__
        
        src_ip = parseIPAddr('src', packet)
        dst_ip = parseIPAddr('dst', packet)
        
        # if packet is destined for container
        if isHostAddr(dst_ip):

            if packet.type == pkt.ethernet.IP_TYPE and (packet.payload.protocol == pkt.ipv4.TCP_PROTOCOL or packet.payload.protocol == pkt.ipv4.UDP_PROTOCOL):

                # allow return traffic for outgoing connections initiated by hosts
                if isHostAddr(src_ip):
                    self.arpTable[(src_ip, packet.payload.next.srcport)] = packet.src
                
                dst_port = packet.payload.next.dstport
                if (dst_ip, dst_port) in self.arpTable:
                    dst_mac = self.arpTable[(dst_ip, dst_port)]
                    print "HOST-FLOW IP {}, HOST-FLOW PORT {}".format(dst_ip, dst_port)
                    if dst_mac in self.macTable:
                        port = self.macTable[(event.dpid, dst_mac)]
                    else:
                        port = of.OFPP_FLOOD
                        
                    sendHostFlow(event, packet, dst_mac, port)
                else:
                    drop(event) 

            # proxy responses to arp requests on behalf of hosts
            # send responses destined to hosts as normal
            elif packet.type == pkt.ethernet.ARP_TYPE:
                if packet.payload.opcode == pkt.arp.REQUEST:
                    proxyArp(event, packet)
                else:
                    send(event, packet, self.macTable[(event.dpid, packet.dst)])

            return

        # non-host-bound traffic
        
        # if origin is host, allow return traffic
        if isHostAddr(src_ip) and packet.type == pkt.ethernet.IP_TYPE and (packet.payload.protocol == pkt.ipv4.TCP_PROTOCOL or packet.payload.protocol == pkt.ipv4.UDP_PROTOCOL) and packet.dst == _dpid_to_mac(event.connection.dpid):
            self.arpTable[(src_ip, packet.payload.next.srcport)] = packet.src
        
        # normal layer 2 forwarding
        dst_mac = packet.dst
        
        if (event.dpid, dst_mac) in self.macTable:
            send(event, packet, self.macTable[(event.dpid, dst_mac)])
        else:
            flood(event)

    # listens to flow statistics from switches
    def _handle_FlowStatsReceived(self, event):
        print("flow stats received")
        self.flowstats = event
        for f in event.stats:
            if f.match.nw_proto == 1: print f.match.__dict__

    # initiates a request for flow statistics for a specific switch
    def requestStats(self, connection):
        connection.send(of.ofp_stats_request(body=of.ofp_flow_stats_request()))

    # initiates a request for flow statistics for all switches
    def requestAllStats(self):
        for con in self.connections:
            self.requestStats(con) 

class l2_learning (object):
    """
    Waits for OpenFlow switches to connect and makes them learning switches
    """
    def __init__ (self, transparent):
        core.openflow.addListeners(self)
        self.transparent = transparent
        self.my_switch = None

    def _handle_ConnectionUp (self, event):
        log.debug("Connection %s" % (event.connection,))
        print("handle connection up")
        self.lastConnectionEvent = event
        if self.my_switch is None:
            self.my_switch = LearningSwitch(event.connection, self.transparent)
        else:
            self.my_switch.addSwitch(event.connection)

def launch (transparent=False, hold_down=_flood_delay):
    """
    Starts module for controlling switches
    """
    try:
        global _flood_delay
        _flood_delay = int(str(hold_down), 10)
        assert _flood_delay >= 0
    except:
        raise RuntimeError("Expected hold-down to be a number")

    core.registerNew(l2_learning, str_to_bool(transparent))
