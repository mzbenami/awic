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

HOST_GATEWAY_IP = '172.16.56.1'
HOST_GATEWAY_NET = '172.16.56.0'
HOST_GATEWAY_MASK = '24'

def _dpid_to_mac (dpid):
  # Should maybe look at internal port MAC instead?
  return EthAddr("%012x" % (dpid & 0xffFFffFFffFF,))

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
		self.arpTable = {}
		self.addSwitch(connection)

		
	def addSwitch(self, connection):
		connection.addListeners(self)
		switch = self.ConnectedSwitch(connection)
		self.switches[connection.dpid] = switch
		self.arpTable[switch.ipaddr] = self.Entry(switch.mac, switch.port)
	
	def _handle_PacketIn(self, event):
		self.lastPacketIn = event
		packet = event.parsed
		local_ip = self.switches[event.connection.dpid].ipaddr
		local_mac = self.switches[event.connection.dpid].mac

		print("handle packet")
                print packet.__dict__

		def proxyArp(packet, connection):
                    
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
                    r.hwsrc = _dpid_to_mac(connection.dpid)
                    e = pkt.ethernet(src = _dpid_to_mac(connection.dpid),
                                dst=a.hwsrc, type = pkt.ethernet.ARP_TYPE)
                    e.payload = r
                    msg = of.ofp_packet_out()
                    msg.data = e.pack()
                    msg.actions.append(of.ofp_action_output(port = self.arpTable[r.protodst].port))
                    print "arp reply" + str(e.__dict__) + str(e.next.__dict__)
                    connection.send(msg)

		def send(packet, connection, dst_ip):
			msg = of.ofp_packet_out()
			msg.data = packet
			if dst_ip in self.arpTable:
				msg.actions.append(of.ofp_action_output(port = self.arpTable[dst_ip].port))
				print "just sent out" + str(self.arpTable[dst_ip].port) + str(dst_ip) + str(packet.dst)
			else:
				msg.actions.append(of.ofp_action_output(port = of.OFPP_FLOOD))
			connection.send(msg)

		def sendHostFlow(event, packet, connection, dst_ip):
			msg = of.ofp_flow_mod()
			msg.match = of.ofp_match.from_packet(packet)
			msg.data = event.ofp
			msg.actions.append(of.ofp_action_dl_addr.set_src(local_mac))
			msg.actions.append(of.ofp_action_dl_addr.set_dst(self.arpTable[dst_ip].mac))
			msg.actions.append(of.ofp_action_output(port = self.arpTable[dst_ip].port))
			connection.send(msg)

		def sendOutFlow(event, packet, connection, dst_ip):
			msg = of.ofp_flow_mod()
			msg.match = of.ofp_match.from_packet(packet)
			msg.data = event.ofp
			if dst_ip in self.arpTable:
				msg.actions.append(of.ofp_action_output(port = self.arpTable[dst_ip].port))
			else:
				msg.actions.append(of.ofp_action_output(port = of.OFPP_LOCAL))
			connection.send(msg)
		
		if packet.type == pkt.ethernet.ARP_TYPE:
			self.arpTable[packet.payload.protosrc] = self.Entry(packet.src, event.port)

			dst_ip = packet.payload.protodst
			src_ip = packet.payload.protosrc
			
			if dst_ip == IPAddr(HOST_GATEWAY_IP):
                            proxyArp(packet, event.connection)

		elif packet.type == pkt.ethernet.IP_TYPE:
			self.arpTable[packet.payload.srcip] = self.Entry(packet.src, event.port)

			dst_ip = packet.payload.dstip
			src_ip = packet.payload.srcip
			if dst_ip.in_network(HOST_GATEWAY_NET, HOST_GATEWAY_MASK):
				if dst_ip == HOST_GATEWAY_IP:
                                    packet.payload.dstip = IPAddr(event.connection.sock.getpeername()[0])
                                    send(packet, event.connection, packet.payload.dstip)
				elif src_ip == local_ip:
					packet.payload.srcip = IPAddr(HOST_GATEWAY_IP)
					send(packet, event.connection, packet.payload.dstip)
				else:
					sendHostFlow(event, packet, event.connection, packet.payload.dstip)
			else:
				sendOutFlow(event, packet, event.connection, packet.payload.dstip)
		else:
			return
			
				
	def _handle_FlowStatsReceived(self, event):
		print("flow stats received")
		self.flowstats = event
		for f in event.stats:
			if f.match.nw_proto == 1: print f.match.__dict__

	def requestStats(self, connection):
		connection.send(of.ofp_stats_request(body=of.ofp_flow_stats_request()))

	def requestAllStats(self):
		for con in self.connections:
			self.requestStats(con) 
class l2_learning (object):
  	"""
  	Waits for OpenFlow switches to connect and makes them learning switches.
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
  Starts an L2 learning switch.
  """
  try:
    global _flood_delay
    _flood_delay = int(str(hold_down), 10)
    assert _flood_delay >= 0
  except:
    raise RuntimeError("Expected hold-down to be a number")

  core.registerNew(l2_learning, str_to_bool(transparent))
