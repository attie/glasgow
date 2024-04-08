import argparse
import logging
from amaranth import *

from ....gateware.pll import *
from ... import *


class SigGenFreqSubtarget(Elaboratable):
    def __init__(self, pads, frequency):
        self.pads = pads
        self.frequency = frequency

    def elaborate(self, platform):
        m = Module()

        m.domains.fout = cd_fout = ClockDomain(reset_less=True)
        m.submodules += PLL(f_in=platform.default_clk_frequency, f_out=self.frequency, odomain="fout")
        platform.add_clock_constraint(cd_fout.clk, self.frequency)

        for c in self.pads.out_t.oe:
            m.d.comb += c.eq(1)
        for c in self.pads.out_t.o:
            m.d.comb += c.eq(cd_fout.clk)

        return m


class SigGenFreqApplet(GlasgowApplet):
    logger = logging.getLogger(__name__)
    help = "signal generator - frequency"
    description = """
    Generate a 50% duty cycle square wave, at the nominated frequency.
    """

    @classmethod
    def add_build_arguments(cls, parser, access):
        super().add_build_arguments(parser, access)

        access.add_pin_set_argument(parser, "out", width=range(1,8), default=(1, ))

        parser.add_argument("-f", "--frequency", metavar="FREQ", type=float, default=16e6,
                            help="generated frequency, in Hz (default: %(default)d Hz)")

    def build(self, target, args):
        self.mux_interface = iface = target.multiplexer.claim_interface(self, args)
        iface.add_subtarget(SigGenFreqSubtarget(
            pads=iface.get_pads(args, pin_sets=("out", )),
            frequency=args.frequency,
        ))

    async def run(self, device, args):
        return await device.demultiplexer.claim_interface(self, self.mux_interface, args)

    async def interact(self, device, args, trigger):
        pass

    @classmethod
    def tests(cls):
        from . import test
        return test.SigGenFreqAppletTestCase
