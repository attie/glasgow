# I2C reference: https://www.nxp.com/docs/en/user-guide/UM10204.pdf

from nmigen.compat import *
from nmigen.compat.genlib.cdc import MultiReg


from .i2c_nmigen import I2CBus

class I2CTarget(Module):
    """
    Simple I2C target.

    Clock stretching is not supported.
    Builtin responses (identification, general call, etc.) are not provided.

    Note that the start, stop, and restart strobes are transaction delimiters rather than direct
    indicators of bus conditions. A transaction always starts with a start strobe and ends with
    either a stop or a restart strobe. That is, a restart strobe, similarly to a stop strobe, may
    be only followed by another start strobe (or no strobe at all if the device is not addressed
    again).

    :attr address:
        The 7-bit address the target will respond to.
    :attr start:
        Start strobe. Active for one cycle immediately after acknowledging address.
    :attr stop:
        Stop stobe. Active for one cycle immediately after a stop condition that terminates
        a transaction that addressed this device.
    :attr restart:
        Repeated start strobe. Active for one cycle immediately after a repeated start condition
        that terminates a transaction that addressed this device.
    :attr write:
        Write strobe. Active for one cycle immediately after receiving a data octet.
    :attr data_i:
        Data octet received from the initiator. Valid when ``write`` is high.
    :attr ack_o:
        Acknowledge strobe. If active for at least one cycle during the acknowledge bit
        setup period (one half-period after write strobe is asserted), acknowledge is asserted.
        Otherwise, no acknowledge is asserted. May use combinatorial feedback from ``write``.
    :attr read:
        Read strobe. Active for one cycle immediately before latching ``data_o``.
    :attr data_o:
        Data octet to be transmitted to the initiator. Latched immedately after receiving
        a read command.
    """
    def __init__(self, pads):
        self.address = Signal(7)
        self.busy    = Signal() # clock stretching request (experimental, undocumented)
        self.start   = Signal()
        self.stop    = Signal()
        self.restart = Signal()
        self.write   = Signal()
        self.data_i  = Signal(8)
        self.ack_o   = Signal()
        self.read    = Signal()
        self.data_o  = Signal(8)
        self.ack_i   = Signal()

        self.submodules.bus = bus = I2CBus(pads)

        ###

        bitno   = Signal(max=8)
        shreg_i = Signal(8)
        shreg_o = Signal(8)

        self.submodules.fsm = FSM(reset_state="IDLE")
        self.fsm.act("IDLE",
            If(bus.start,
                NextState("START"),
            )
        )
        self.fsm.act("START",
            If(bus.stop,
                # According to the spec, technically illegal, "but many devices handle
                # this anyway". Can Philips, like, decide on whether they want it or not??
                NextState("IDLE")
            ).Elif(bus.setup,
                NextValue(bitno, 0),
                NextState("ADDR-SHIFT")
            )
        )
        self.fsm.act("ADDR-SHIFT",
            If(bus.stop,
                NextState("IDLE")
            ).Elif(bus.start,
                NextState("START")
            ).Elif(bus.sample,
                NextValue(shreg_i, (shreg_i << 1) | bus.sda_i),
            ).Elif(bus.setup,
                NextValue(bitno, bitno + 1),
                If(bitno == 7,
                    If(shreg_i[1:] == self.address,
                        self.start.eq(1),
                        NextValue(bus.sda_o, 0),
                        NextState("ADDR-ACK")
                    ).Else(
                        NextState("IDLE")
                    )
                )
            )
        )
        self.fsm.act("ADDR-ACK",
            If(bus.stop,
                self.stop.eq(1),
                NextState("IDLE")
            ).Elif(bus.start,
                self.restart.eq(1),
                NextState("START")
            ).Elif(bus.setup,
                If(~shreg_i[0],
                    NextValue(bus.sda_o, 1),
                    NextState("WRITE-SHIFT")
                )
            ).Elif(bus.sample,
                If(shreg_i[0],
                    NextValue(shreg_o, self.data_o),
                    NextState("READ-STRETCH")
                )
            )
        )
        self.fsm.act("WRITE-SHIFT",
            If(bus.stop,
                self.stop.eq(1),
                NextState("IDLE")
            ).Elif(bus.start,
                self.restart.eq(1),
                NextState("START")
            ).Elif(bus.sample,
                NextValue(shreg_i, (shreg_i << 1) | bus.sda_i),
            ).Elif(bus.setup,
                NextValue(bitno, bitno + 1),
                If(bitno == 7,
                    NextValue(self.data_i, shreg_i),
                    NextState("WRITE-ACK")
                )
            )
        )
        self.comb += self.write.eq(self.fsm.after_entering("WRITE-ACK"))
        self.fsm.act("WRITE-ACK",
            If(bus.stop,
                self.stop.eq(1),
                NextState("IDLE")
            ).Elif(bus.start,
                self.restart.eq(1),
                NextState("START")
            ).Elif(bus.setup,
                NextValue(bus.sda_o, 1),
                NextState("WRITE-SHIFT")
            ).Elif(~bus.scl_i,
                NextValue(bus.scl_o, ~self.busy),
                If(self.ack_o,
                    NextValue(bus.sda_o, 0)
                )
            )
        )
        self.comb += self.read.eq(self.fsm.before_entering("READ-STRETCH"))
        self.fsm.act("READ-STRETCH",
            If(self.busy,
                NextValue(shreg_o, self.data_o)
            ),
            If(bus.stop,
                self.stop.eq(1),
                NextState("IDLE")
            ).Elif(bus.start,
                NextState("START")
            ).Elif(self.busy,
                If(~bus.scl_i,
                    NextValue(bus.scl_o, 0)
                )
            ).Else(
                If(~bus.scl_i,
                    NextValue(bus.sda_o, shreg_o[7])
                ),
                NextValue(bus.scl_o, 1),
                NextState("READ-SHIFT")
            )
        )
        self.fsm.act("READ-SHIFT",
            If(bus.stop,
                self.stop.eq(1),
                NextState("IDLE")
            ).Elif(bus.start,
                self.restart.eq(1),
                NextState("START")
            ).Elif(bus.setup,
                NextValue(bus.sda_o, shreg_o[7]),
            ).Elif(bus.sample,
                NextValue(shreg_o, shreg_o << 1),
                NextValue(bitno, bitno + 1),
                If(bitno == 7,
                    NextState("READ-ACK")
                )
            )
        )
        self.fsm.act("READ-ACK",
            If(bus.stop,
                self.stop.eq(1),
                NextState("IDLE")
            ).Elif(bus.start,
                self.restart.eq(1),
                NextState("START")
            ).Elif(bus.setup,
                NextValue(bus.sda_o, 1),
            ).Elif(bus.sample,
                If(~bus.sda_i,
                    NextValue(shreg_o, self.data_o),
                    NextState("READ-STRETCH")
                ).Else(
                    self.stop.eq(1),
                    NextState("IDLE")
                )
            )
        )
