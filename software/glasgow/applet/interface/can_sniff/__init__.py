import os
import sys
import logging
import asyncio
import argparse
from nmigen import *
from nmigen.lib.cdc import FFSynchronizer

from ....support.endpoint import *
from ....gateware.pads import *
from ....gateware.uart import *
from ... import *


# Cat() will concatenate 1,0,1 -> 0x05
# x[-1]  addresses the MSB
# x[:-1] will strip the MSB off
# x[0]   addresses the LSB
# x.eq(Cat(Const(1, unsigned(1)), x[:-1]))
#      will shift left, and insert '1' in LSB
#      0b0101 -> 0b1011


class CANBus(Elaboratable):
    def __init__(self, pads):
        self.rx_t = pads.rx_t
        self.rx_i = Signal()

        self.tx_t = pads.tx_t
        self.tx_o = Signal(reset=1)

        self.term_t = pads.term_t
        self.term_o = Signal(reset=0) # TODO: return to 0 / set from CLI

    def elaborate(self, platform):
        m = Module()

        m.d.comb += self.rx_t.oe.eq(0)
        m.submodules += FFSynchronizer(self.rx_t.i, self.rx_i, reset=1)

        m.d.comb += self.tx_t.oe.eq(1)
        m.d.comb += self.tx_t.o.eq(self.tx_o)

        m.d.comb += self.term_t.oe.eq(1)
        m.d.comb += self.term_t.o.eq(self.term_o)

        return m


class CANTiming(Elaboratable):
    def __init__(self, bus):
        self.rx_trigger = ~bus.rx_i # effectively CAN_H
        self.run        = Signal()  # continue running? assert while in frame

        self.idle            = Signal()        # timing in idle
        self.boundary_stb    = Signal(reset=0) # strobe for rx bit boundary
        self.sample_stb      = Signal(reset=0) # strobe for rx bit sample point

    def elaborate(self, platform):
        baudrate = 250000              # TODO: make variable, currently hard coded to 250 kbit/s
        quanta = baudrate * 10         # x10 is to permit time quanta in bit time
        bit_cyc = round(platform.default_clk_frequency / quanta) # ~19 for 250 kbit/s

        # TODO: make this configurable
        # <-- bit boundary
        sync = 1
        prop = 3
        seg1 = 3
        # <-- sample point
        seg2 = 3
        # <-- bit boundary

        bit_setup_cyc  = (sync + prop + seg1       ) * bit_cyc # bit boundary to sample point
        bit_period_cyc = (sync + prop + seg1 + seg2) * bit_cyc # bit boundray to next bit boundary

        m = Module()

        ctr = Signal(32)

        with m.FSM() as fsm:
            m.d.comb += self.idle.eq(fsm.ongoing("IDLE"))

            with m.State("IDLE"):
                m.d.sync += ctr.eq(0)
                with m.If(self.rx_trigger):
                    m.d.comb += self.boundary_stb.eq(1)
                    m.next = "RUN"

            with m.State("RUN"):
                m.d.sync += ctr.eq(ctr + 1)

                with m.If(ctr == bit_setup_cyc):
                    m.d.comb += self.sample_stb.eq(1)

                with m.If(ctr >= bit_period_cyc):
                    m.d.comb += self.boundary_stb.eq(1)
                    m.d.sync += ctr.eq(0)

                    with m.If(~self.run):
                        m.next = "IDLE"

        return m


class CANDeStuff(Elaboratable):
    def __init__(self, bus, timing):
        self.bus = bus
        self.timing = timing

        self.sample_stb = Signal()
        self.stuff_err = Signal()

    def elaborate(self, platform):
        # raw:     00000 00
        # stuffed: 00000100

        # raw:     11111 11
        # stuffed: 11111011

        m = Module()

        last_bit = Signal()
        stable_ctr = Signal(3)

        sample_gate = stable_ctr < 4 # 5-1, because we need to gate the stobe
        m.d.sync += self.sample_stb.eq(self.timing.sample_stb & sample_gate)

        with m.If(self.timing.idle):
            m.d.sync += [
                last_bit.eq(1),
                stable_ctr.eq(0),
            ]

        with m.Elif(self.timing.sample_stb):
            m.d.sync += last_bit.eq(self.bus.rx_i)
            with m.If(last_bit != self.bus.rx_i):
                m.d.sync += stable_ctr.eq(0)
            with m.Elif(stable_ctr >= 5):
                # ERROR! this should be a stuffed bit, but it wasn't ... tsk tsk
                # TODO: make this blow up
                m.d.sync += stable_ctr.eq(0)
                m.d.sync += self.stuff_err.eq(1)
            with m.Else():
                m.d.sync += stable_ctr.eq(stable_ctr + 1)

        return m


class CANLowLevel(Elaboratable):
    def __init__(self, bus):
        self.bus = bus

        self.rx_rdy = Signal(reset=0)      # strobe for rx bits, excluding stuffed
        self.rx_rdy_raw = Signal(reset=0)  # strobe for all rx bits, including stuffed
        self.rx_data = Signal(32)          # TODO: remove this / move it out into another module??

        self.timing = CANTiming(bus)
        self.destuff = CANDeStuff(bus, self.timing)

    def elaborate(self, platform):
        m = Module()
        m.submodules += self.timing
        m.submodules += self.destuff

        with m.FSM() as fsm:
            with m.State("IDLE"):
                m.d.sync += [
                    self.rx_data.eq(0),
                ]
                with m.If(self.timing.boundary_stb):
                    m.next = "SETUP"

            with m.State("SETUP"):
                with m.If(self.destuff.sample_stb):
                    m.d.sync += self.rx_data.eq(Cat(self.bus.rx_i, self.rx_data[:-1]))
                    m.next = "BIT_SAMPLE"

            with m.State("BIT_SAMPLE"):
                m.d.comb += self.rx_rdy.eq(1)
                m.next = "BIT_WAIT"

            with m.State("BIT_WAIT"):
                with m.If(self.timing.boundary_stb):
                    with m.If(~self.timing.run):
                        m.next = "IDLE"
                    with m.Else():
                        m.next = "SETUP"

        return m


class CANCRC(Elaboratable):
    def __init__(self, ll):
        self.ll = ll

        self.rst = Signal()
        self.run = Signal()
        self.out = Signal(15)

    def elaborate(self, platform):
        m = Module()

        with m.If(self.rst):
            m.d.sync += self.out.eq(0)
        with m.Elif(self.run & self.ll.rx_rdy):
            new_bit = self.ll.bus.rx_i
            next_out = Cat(Const(0, unsigned(1)), self.out[:-1])
            with m.If(new_bit ^ self.out[-1]):
                m.d.sync += self.out.eq(next_out ^ Const(0x4599, unsigned(15)))
            with m.Else():
                m.d.sync += self.out.eq(next_out)

        return m


class CANSubtarget(Elaboratable):
    def __init__(self, pads, out_fifo, in_fifo,
                 manual_cyc, bit_cyc, rx_errors):
        self.out_fifo = out_fifo
        self.in_fifo = in_fifo
        self.manual_cyc = manual_cyc
        self.bit_cyc = bit_cyc
        self.rx_errors = rx_errors

        self.can_bus = CANBus(pads)

        self.pads = pads

    def elaborate(self, platform):
        m = Module()

        m.submodules.bus = bus = self.can_bus
        m.submodules.ll = ll = CANLowLevel(bus)
        m.submodules.crc = crc = CANCRC(ll)

        m.d.comb += [
            self.pads.dbgsp_t.oe.eq(1),
            self.pads.dbgsp_t.o.eq(ll.destuff.sample_stb),
            #self.pads.dbgsp_t.o.eq(crc.run),
            #self.pads.dbgsp_t.o.eq(ll.bit_boundary),

            self.pads.dbgarb_t.oe.eq(1),
        ]

        ctr = Signal(32)

        ctl_dlc = Signal(4)

        with m.FSM() as fsm:
            m.d.comb += ll.timing.run.eq(~fsm.ongoing("IDLE"))
            m.d.comb += crc.rst.eq(fsm.ongoing("IDLE"))
            m.d.comb += self.pads.dbgarb_t.o.eq(fsm.ongoing("IDLE"))
            #m.d.comb += self.pads.dbgarb_t.o.eq(fsm.ongoing("ARBITRATION-ID"))
            #m.d.comb += self.pads.dbgarb_t.o.eq(fsm.ongoing("ACK-END"))
            #m.d.comb += self.pads.dbgarb_t.o.eq(fsm.ongoing("ARBITRATION-ID"))
            #m.d.comb += self.pads.dbgarb_t.o.eq(fsm.ongoing("ACK-WAIT-FOR-BEGIN"))
            #m.d.comb += self.pads.dbgarb_t.o.eq(fsm.ongoing("ACK-WAIT-FOR-END"))

            with m.State("IDLE"):
                with m.If(ll.timing.rx_trigger):
                    m.d.sync += ctr.eq(10 + 1) # 1 is for SOF
                    m.d.sync += crc.run.eq(1)
                    m.next = "ARBITRATION-ID"

            with m.State("ARBITRATION-ID"):
                with m.If(ll.rx_rdy):
                    m.d.sync += ctr.eq(ctr - 1)

                    # 10 9 8
                    with m.If(ctr == 8):
                        m.d.comb += [
                            self.in_fifo.w_data.eq(Cat(ll.rx_data[:3], Const(0, unsigned(5)))),
                            self.in_fifo.w_en.eq(1),
                        ]

                    # 7 6 5 4 3 2 1 0
                    with m.If(ctr == 0):
                        m.d.comb += [
                            self.in_fifo.w_data.eq(ll.rx_data[:8]),
                            self.in_fifo.w_en.eq(1),
                        ]

                        m.d.sync += ctr.eq(6)
                        m.next = "ARBITRATION-CONTROL"

            with m.State("ARBITRATION-CONTROL"):
                with m.If(ll.rx_rdy):
                    m.d.sync += ctr.eq(ctr - 1)

                    with m.If(ctr == 0):
                        m.d.comb += [
                            self.in_fifo.w_data.eq(Cat(ll.rx_data[:7], Const(0, unsigned(1)))),
                            self.in_fifo.w_en.eq(1),
                        ]

                        with m.If(ll.rx_data[:4] == 0):
                            m.d.sync += ctr.eq(14)
                            m.next = "CRC"
                        with m.Elif(ll.rx_data[:4] > 8):
                            m.next = "IDLE-WAIT-INIT" # <-- this is illegal
                        with m.Else():
                            m.d.sync += ctl_dlc.eq(ll.rx_data[:4] - 1)
                            m.d.sync += ctr.eq(7)
                            m.next = "DATA"

            with m.State("DATA"):
                with m.If(ll.rx_rdy):
                    m.d.sync += ctr.eq(ctr - 1)

                    with m.If(ctr == 0):
                        m.d.comb += [
                            self.in_fifo.w_data.eq(ll.rx_data[:8]),
                            self.in_fifo.w_en.eq(1),
                        ]

                        m.d.sync += ctl_dlc.eq(ctl_dlc - 1)

                        with m.If(ctl_dlc > 0):
                            m.d.sync += ctr.eq(7)

                        with m.Else():
                            m.d.sync += ctr.eq(14)
                            m.next = "CRC"

            with m.State("CRC"):
                with m.If(ll.rx_rdy):
                    m.d.sync += ctr.eq(ctr - 1)

                    with m.If(ctr == 8):
                        m.d.comb += [
                            self.in_fifo.w_data.eq(Cat(ll.rx_data[:7], Const(0, unsigned(1)))),
                            self.in_fifo.w_en.eq(1),
                        ]

                    with m.If(ctr == 0):
                        m.d.comb += [
                            self.in_fifo.w_data.eq(ll.rx_data[:8]),
                            self.in_fifo.w_en.eq(1),
                        ]

                        m.d.sync += crc.run.eq(0)
                        m.next = "CRC-1"

            with m.State("CRC-1"):
                m.d.comb += [
                    self.in_fifo.w_data.eq(crc.out == 0),
                    self.in_fifo.w_en.eq(1),
                ]
                m.next = "IDLE-WAIT-INIT"

            with m.State("IDLE-WAIT-INIT"):
                m.d.sync += ctr.eq(8)
                m.next = "IDLE-WAIT"

            with m.State("IDLE-WAIT"):
                with m.If(ll.rx_rdy):
                    m.d.sync += ctr.eq(ctr - 1)
                    
                    with m.If(ctr == 0):
                        m.next = "IDLE"

        return m


class CANSniffApplet(GlasgowApplet, name="can-sniff"):
    logger = logging.getLogger(__name__)
    help = "communicate via CAN"
    description = """
    Receive data via CAN.
    """

    __pins = ("tx", "rx", "term", "dbgsp", "dbgarb")

    @classmethod
    def add_build_arguments(cls, parser, access):
        super().add_build_arguments(parser, access)

        for pin in cls.__pins:
            access.add_pin_argument(parser, pin, default=True)

        parser.add_argument(
            "-b", "--bitrate", metavar="RATE", type=int, default=250000,
            help="set bit rate to RATE bits per second (default: %(default)s)")
        parser.add_argument(
            "--tolerance", metavar="PPM", type=int, default=50000,
            help="verify that actual baud rate is within PPM parts per million of specified"
                 " (default: %(default)s)")

    def build(self, target, args):
        self.__sys_clk_freq = target.sys_clk_freq

        manual_cyc, self.__addr_manual_cyc = target.registers.add_rw(32)

        bit_cyc,    self.__addr_bit_cyc    = target.registers.add_ro(32)
        rx_errors,  self.__addr_rx_errors  = target.registers.add_ro(16)

        self.mux_interface = iface = target.multiplexer.claim_interface(self, args)
        subtarget = iface.add_subtarget(CANSubtarget(
            pads=iface.get_pads(args, pins=self.__pins),
            out_fifo=iface.get_out_fifo(),
            in_fifo=iface.get_in_fifo(),
            manual_cyc=manual_cyc,
            bit_cyc=bit_cyc,
            rx_errors=rx_errors,
        ))

    async def run(self, device, args):
        # Load the manually set baud rate.
        manual_cyc = self.derive_clock(
            input_hz=self.__sys_clk_freq, output_hz=args.bitrate,
            min_cyc=2, max_deviation_ppm=args.tolerance)
        await device.write_register(self.__addr_manual_cyc, manual_cyc, width=4)

        iface = await device.demultiplexer.claim_interface(self, self.mux_interface, args)

        return iface

    async def spacer(self):
        while True:
            await asyncio.sleep(0.5)
            print('---')

    async def interact(self, device, args, uart):
        asyncio.create_task(self.spacer())

        while True:
            fid = (await uart.read(2))[:]
            flen = (await uart.read(1))[0] & 0x0f # pretend that remote and extended id are always zero
            fdata = (await uart.read(flen))[:]
            fcrc = (await uart.read(2))[:]
            fflags = (await uart.read(1))[0]

            frame_id = (fid[0] << 8) | fid[1]
            frame_crc = (fcrc[0] << 8) | fcrc[1]

            print(f'{frame_id=:03x}')
            print(f'{flen=:d}')
            for i, b in enumerate(fdata):
                print(f'  fdata[{i}]={fdata[i]:02x}')
            print(f'{frame_crc=:04x}')
            print(f'crc valid? {("no","yes")[fflags&0x01]}')
            print(f'====')
