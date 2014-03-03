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




class LearningSwitch(obect):
	def __init__ (self, connection, transparent, event):
		self.connection = connection
		self.transparent = transparent
		self.event = event

		connection.addListeners(self)

	def _handlePacketIn(self, event):
		print(dir(event))
		log.debug("Hello from LearningSwitch")

class l2_learning (object):
  """
  Waits for OpenFlow switches to connect and makes them learning switches.
  """
  def __init__ (self, transparent):
    core.openflow.addListeners(self)
    self.transparent = transparent

  def _handle_ConnectionUp (self, event):
    log.debug("Connection %s" % (event.connection,))
    self.myswitch = LearningSwitch(event.connection, self.transparent, event

  def _handle_PacketIn (self, event):
  	print(dir(event))
  	log.debug("Hello from l2_learning!")

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