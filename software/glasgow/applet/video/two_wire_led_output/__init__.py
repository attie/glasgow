import logging
import asyncio
from nmigen import *

from ....support.endpoint import *
from ....gateware.pads import *
from ....gateware.pll import *
from ... import *

class Video2WireLEDOutput(Elaboratable):
    def __init__(self, pads, out):
        self.pads = pads
        self.out = out

    def elaborate(self, platform):
        m = Module()

        m.d.comb += [
            self.pads.out_t.oe.eq(1),
            self.pads.out_t.o.eq(~self.out),
        ]

        return m

class Video2WireLEDOutputSubtarget(Elaboratable):
    def __init__(self, pads, addr, red, green, blue):
        self.pads = pads

        self.addr = addr

        self.red = red
        self.green = green
        self.blue = blue

        print(f'{addr=}')
        print(f'{red=}')
        print(f'{green=}')
        print(f'{blue=}')

    def elaborate(self, platform):
        m = Module()

        out = Signal()
        m.submodules += Video2WireLEDOutput(self.pads, out)

        sys_clk_freq = platform.default_clk_frequency

        t_init = int(1 + sys_clk_freq * 250e-6)

        t_clk_lo = int(1 + sys_clk_freq * 60e-6)
        t_clk_hi = int(1 + sys_clk_freq * 70e-6)

        t_dat_lo  = int(1 + sys_clk_freq * 1600e-9)
        t_dat_hi0 = int(1 + sys_clk_freq * 3400e-9)
        t_dat_hi1 = int(1 + sys_clk_freq * 1000e-9)
        t_dat_wait = int(1 + sys_clk_freq * 7000e-9)

        cyc_cnt = Signal(32)
        clk_cnt = Signal(32)
        bit_cnt = Signal(range(8))

        word = Signal(8)

        with m.FSM():
            with m.State("INIT-1"):
                m.d.comb += out.eq(1)
                m.d.sync += [
                    cyc_cnt.eq(0),
                    clk_cnt.eq(0),
                    bit_cnt.eq(0),
                    word.eq(Cat(self.red, self.green, self.blue, self.addr)),
                ]
                #m.next = "INIT-2"
                m.next = "DATA-LO"

            with m.State("INIT-2"):
                m.d.comb += out.eq(1)
                with m.If(cyc_cnt < t_init):
                    m.d.sync += cyc_cnt.eq(cyc_cnt + 1)
                with m.Else():
                    m.d.sync += cyc_cnt.eq(0)
                    m.next = "I-CLK-LO"

            with m.State("I-CLK-LO"):
                m.d.comb += out.eq(0)
                with m.If(cyc_cnt < t_clk_lo):
                    m.d.sync += cyc_cnt.eq(cyc_cnt + 1)
                with m.Else():
                    m.d.sync += cyc_cnt.eq(0)
                    m.next = "I-CLK-HI"

            with m.State("I-CLK-HI"):
                m.d.comb += out.eq(1)
                with m.If(cyc_cnt < t_clk_hi):
                    m.d.sync += cyc_cnt.eq(cyc_cnt + 1)
                with m.Else():
                    m.d.sync += cyc_cnt.eq(0)
                    m.d.sync += clk_cnt.eq(clk_cnt + 1)
                    with m.If(clk_cnt < 100):
                        m.next = "I-CLK-LO"
                    with m.Else():
                        m.next = "DATA-LO"

            with m.State("DATA-LO"):
                m.d.comb += out.eq(0)
                with m.If(cyc_cnt < t_dat_lo):
                    m.d.sync += cyc_cnt.eq(cyc_cnt + 1)
                with m.Else():
                    m.d.sync += cyc_cnt.eq(0)
                    m.d.sync += word.eq(Cat(0, word[:-1]))
                    #m.d.sync += word.eq(word << 1)

                    # 8421 8421
                    # 0101 1010

                    with m.If(word[-1]): # inversion is intentional!
                        m.next = "DATA-HI-1"
                    with m.Else():
                        m.next = "DATA-HI-0"

            with m.State("DATA-HI-0"):
                m.d.comb += out.eq(1)
                with m.If(cyc_cnt < t_dat_hi0):
                    m.d.sync += cyc_cnt.eq(cyc_cnt + 1)
                with m.Else():
                    m.d.sync += cyc_cnt.eq(0)

                    m.d.sync += bit_cnt.eq(bit_cnt + 1)
                    with m.If(bit_cnt == 7):
                        m.next = "DATA-WAIT"
                    with m.Else():
                        m.next = "DATA-LO"

            with m.State("DATA-HI-1"):
                m.d.comb += out.eq(1)
                with m.If(cyc_cnt < t_dat_hi1):
                    m.d.sync += cyc_cnt.eq(cyc_cnt + 1)
                with m.Else():
                    m.d.sync += cyc_cnt.eq(0)

                    m.d.sync += bit_cnt.eq(bit_cnt + 1)
                    with m.If(bit_cnt == 7):
                        m.next = "DATA-WAIT"
                    with m.Else():
                        m.next = "DATA-LO"

            with m.State("DATA-WAIT"):
                m.d.comb += out.eq(0)
                with m.If(cyc_cnt < t_dat_wait):
                    m.d.sync += cyc_cnt.eq(cyc_cnt + 1)
                with m.Else():
                    m.d.sync += cyc_cnt.eq(0)
                    #m.next = "CLK-HI"
                    m.next = "STOP"

            with m.State("STOP"):
                m.d.comb += out.eq(1)

            with m.State("CLK-LO"):
                m.d.comb += out.eq(0)
                with m.If(cyc_cnt < t_clk_lo):
                    m.d.sync += cyc_cnt.eq(cyc_cnt + 1)
                with m.Else():
                    m.d.sync += cyc_cnt.eq(0)
                    m.next = "CLK-HI"

            with m.State("CLK-HI"):
                m.d.comb += out.eq(1)
                with m.If(cyc_cnt < t_clk_hi):
                    m.d.sync += cyc_cnt.eq(cyc_cnt + 1)
                with m.Else():
                    m.d.sync += cyc_cnt.eq(0)
                    m.next = "CLK-LO"

        print(f'{t_clk_lo=}')
        print(f'{t_clk_hi=}')

        return m


class Video2WireLEDOutputApplet(GlasgowApplet, name="video-2wire-led-output"):
    logger = logging.getLogger(__name__)
    help = "display video via unknown 2-Wire LEDs"
    description = "..."
    preview = True

    __pins = ("out",)

    @classmethod
    def add_build_arguments(cls, parser, access):
        super().add_build_arguments(parser, access)

        access.add_pin_argument(parser, "out", default=0)

        parser.add_argument(
            "-a", "--addr", metavar="ADDR", type=int, required=True,
            help="address of LED(s)")
        parser.add_argument(
            "-r", "--red", metavar="RED", type=int, required=True,
            help="enable the red diode(s)?")
        parser.add_argument(
            "-g", "--green", metavar="GREEN", type=int, required=True,
            help="enable the green diode(s)?")
        parser.add_argument(
            "-b", "--blue", metavar="BLUE", type=int, required=True,
            help="enable the blue diode(s)?")

    def build(self, target, args):
        self.mux_interface = iface = target.multiplexer.claim_interface(self, args)
        subtarget = iface.add_subtarget(Video2WireLEDOutputSubtarget(
            pads=iface.get_pads(args, pins=self.__pins),
            addr=args.addr,
            red=args.red,
            green=args.green,
            blue=args.blue,
        ))

        return subtarget

    async def run(self, device, args):
        return await device.demultiplexer.claim_interface(self, self.mux_interface, args)

    #async def interact(self, device, args, leds):
    #    await asyncio.sleep(2)

