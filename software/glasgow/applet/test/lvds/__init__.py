import logging
from amaranth import *
from amaranth.build import *

from ... import *

class LvdsSubtarget(Elaboratable):
    def __init__(self, lvds_pin):
        self.lvds_pin = lvds_pin

    def elaborate(self, platform):
        m = Module()

        ctr = Signal(24)
        m.d.sync += ctr.eq(ctr + 1)
        m.d.comb += self.lvds_pin.io.eq(ctr[22])

        return m

class LvdsApplet(GlasgowApplet):
    logger = logging.getLogger(__name__)
    help = "demonstrate LVDS I/O"
    description = "..."

    def build(self, target, args):
        # setup the LVDS resource(s)
        lvds_res = Resource("lvds", 0,
            Subsignal("io", Pins("3", dir="o", conn=("lvds", 0))),
            Attrs(IO_STANDARD="SB_LVCMOS33"),
        )
        target.platform.add_resources([ lvds_res ])

        # get the resource(s)
        lvds_pin = target.platform.request("lvds")

        self.mux_interface = iface = target.multiplexer.claim_interface(self, args)
        subtarget = iface.add_subtarget(LvdsSubtarget(lvds_pin))
        return subtarget

    async def run(self, device, args):
        return await device.demultiplexer.claim_interface(self, self.mux_interface, args)
