import logging
import asyncio
from nmigen import *

from ... import *

class ServoPPMOutput(Elaboratable):
    def __init__(self, pads, out):
        self.pads = pads
        self.out = out

    def elaborate(self, platform):
        m = Module()

        m.d.comb += [
            self.pads.out_t.oe.eq(1),
            self.pads.out_t.o.eq(self.out),
        ]

        return m

class ServoPPMOutputSubtarget(Elaboratable):
    def __init__(self, pads):
        self.pads = pads

    def elaborate(self, platform):
        m = Module()

        out = Signal()
        m.submodules += ServoPPMOutput(self.pads, out)

        sys_clk_freq = platform.default_clk_frequency

        t_step = 1000
        t_min = int(1 + sys_clk_freq * 1e-3)
        t_max = int(1 + sys_clk_freq * 2e-3)

        t_cyc = int(1 + sys_clk_freq * 20e-3)

        cyc_cnt = Signal(32)
        pos_cnt = Signal(32)

        with m.FSM():
            with m.State("INIT"):
                m.d.sync += [
                    cyc_cnt.eq(0),
                    pos_cnt.eq(t_min),
                ]
                m.next = "UP"

            with m.State("UP"):
                m.d.sync += cyc_cnt.eq(cyc_cnt + 1)
                with m.If(cyc_cnt < pos_cnt):
                    m.d.comb += out.eq(1)
                with m.Elif(cyc_cnt < t_cyc):
                    m.d.comb += out.eq(0)
                with m.Elif(pos_cnt >= t_max):
                    m.d.sync += cyc_cnt.eq(0)
                    m.next = "DOWN"
                with m.Else():
                    m.d.sync += cyc_cnt.eq(0)
                    m.d.sync += pos_cnt.eq(pos_cnt + t_step)

            with m.State("DOWN"):
                m.d.sync += cyc_cnt.eq(cyc_cnt + 1)
                with m.If(cyc_cnt < pos_cnt):
                    m.d.comb += out.eq(1)
                with m.Elif(cyc_cnt < t_cyc):
                    m.d.comb += out.eq(0)
                with m.Elif(pos_cnt <= t_min):
                    m.d.sync += cyc_cnt.eq(0)
                    m.next = "UP"
                with m.Else():
                    m.d.sync += cyc_cnt.eq(0)
                    m.d.sync += pos_cnt.eq(pos_cnt - t_step)

        return m


class ControlServoPPMOutputApplet(GlasgowApplet, name="control-servo-ppm-output"):
    logger = logging.getLogger(__name__)
    help = ""
    description = "..."
    preview = True

    __pins = ("out",)

    @classmethod
    def add_build_arguments(cls, parser, access):
        super().add_build_arguments(parser, access)

        access.add_pin_argument(parser, "out", default=0)

    def build(self, target, args):
        self.mux_interface = iface = target.multiplexer.claim_interface(self, args)
        subtarget = iface.add_subtarget(ServoPPMOutputSubtarget(
            pads=iface.get_pads(args, pins=self.__pins),
        ))

        return subtarget

    async def run(self, device, args):
        return await device.demultiplexer.claim_interface(self, self.mux_interface, args)

    #async def interact(self, device, args, leds):
    #    await asyncio.sleep(2)

