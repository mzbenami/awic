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


class LearningSwitch(object):
	def __init__ (self, connection, transparent):
		self.transparent = transparent
		self.connections = []
		self.macTable = {}
		self.addConnection(connection)
		
	
	def addBroadcastFlow(self, event):
		
		msg = of.ofp_flow_mod()
		msg.match = of.ofp_match.from_packet(event.parsed, event.ofp.in_port)
		msg.data = event.ofp
		msg.actions.append(of.ofp_action_output(port = of.OFPP_ALL))
		event.connection.send(msg)
		
	def addMacTableFlow(self, event):
		msg = of.ofp_flow_mod()
		msg.match = of.ofp_match.from_packet(event.parsed, event.ofp.in_port)
		msg.data = event.ofp
		msg.actions.append(of.ofp_action_output(port = self.macTable[event.parsed.dst]))
		event.connection.send(msg)

	def flood(self, event):
		print ("flooding!")
		msg = of.ofp_packet_out()
		msg.data = event.ofp
		msg.actions.append(of.ofp_action_output(port = of.OFPP_ALL))
		event.connection.send(msg)

	def addConnection(self, connection):
		self.connections.append(connection)
		connection.addListeners(self)
	
	def printPacket(self, packet):
		if (packet.type == pkt.ethernet.ARP_TYPE):
			srcip = "arp"
			dstip = "arp"
		else:
			srcip, dstip = packet.payload.srcip, packet.payload.dstip
		print("Src: {}, Dst: {}, SrcIp: {}, DstIp: {}".format(packet.src, packet.dst, str(srcip), str(dstip)))	

	def _handle_PacketIn(self, event):
		self.lastPacketIn = event
		packet = event.parsed

		print("handle packet")
		self.printPacket(packet)
		
		self.macTable[packet.src] = event.ofp.in_port

		if packet.dst == EthAddr("FF:FF:FF:FF:FF:FF"):
			self.addBroadcastFlow(event)
		elif packet.dst in self.macTable:
			self.addMacTableFlow(event)
		else:
			self.flood(event)

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
			self.my_switch.addConnection(event.connection)

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
