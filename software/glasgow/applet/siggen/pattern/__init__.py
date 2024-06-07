import argparse
import logging
from amaranth import *

from ....gateware.pll import *
from ... import *


class SigGenPatternSubtarget(Elaboratable):
    def __init__(self, pads, frequency, pattern, invert):
        self.pads = pads
        self.frequency = frequency
        self.pattern = pattern
        self.invert = invert

    def elaborate(self, platform):
        m = Module()

        m.domains.fout = cd_fout = ClockDomain(reset_less=True)
        m.submodules += PLL(f_in=platform.default_clk_frequency, f_out=self.frequency, odomain="fout")
        platform.add_clock_constraint(cd_fout.clk, self.frequency)

        pattern = Signal(len(self.pattern), reset=int(self.pattern, 2))
        m.d.fout += pattern.eq(Cat(pattern[-1], pattern[:-1]))

        for c in self.pads.out_t.oe:
            m.d.comb += c.eq(1)
        for c in self.pads.out_t.o:
            m.d.comb += c.eq(~pattern[0] if self.invert else pattern[0])

        return m


class SigGenPatternApplet(GlasgowApplet):
    logger = logging.getLogger(__name__)
    help = "signal generator - pattern"
    description = """
    Generate a digital pattern, stepping at the nominated frequency.
    """

    @classmethod
    def add_build_arguments(cls, parser, access):
        super().add_build_arguments(parser, access)

        access.add_pin_set_argument(parser, "out", width=range(1,8), default=(1, ))

        parser.add_argument("-f", "--frequency", metavar="FREQ", type=float, default=16e6,
                            help="generated frequency, in Hz (default: %(default)d Hz)")
        parser.add_argument("-p", "--pattern", metavar="PATTERN", type=str, default="1111010000",
                            help="the arbitary pattern to play out, right-shift (default: %(default)s)")
        parser.add_argument("-i", "--invert", action="store_true",
                            help="invert the given pattern")

    def build(self, target, args):
        self.mux_interface = iface = target.multiplexer.claim_interface(self, args)
        iface.add_subtarget(SigGenPatternSubtarget(
            pads=iface.get_pads(args, pin_sets=("out", )),
            frequency=args.frequency,
            pattern=args.pattern,
            invert=args.invert,
        ))

    async def run(self, device, args):
        return await device.demultiplexer.claim_interface(self, self.mux_interface, args)

    async def interact(self, device, args, trigger):
        pass

    @classmethod
    def tests(cls):
        from . import test
        return test.SigGenPatternAppletTestCase
