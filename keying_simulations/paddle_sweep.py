"""A sweep of keying simulations, at 30 WPM unless told otherwise.

Six scenarios, chosen by the third argument, a speed in words a
minute by an optional fourth, and the Dit Mem % setting by an optional
fifth -- the keyer's own default of 0 where it is not given:

  tap      the dit paddle is held closed throughout and the dah paddle
           is tapped for 5ms
  dit-tap  the mirror of it: the dah paddle held and the dit tapped
  swap     the dit paddle is released at the same instant the dah
           paddle is closed, and the dah is then held
  squeeze  both paddles closed at time zero and both let go together
  dah-first
           the dah paddle closed at time zero and the dit closed
           after it, both held and let go together
  stall    an S and then a T, through the MIDI path and timed by the
           device, with the whole process stalled from just before the
           S's dit is let go of until the moment in question

The moment in question moves 4ms per run. Each run drives the real
Keyer over a virtual clock and writes a plot of what the operator did,
what they heard, and what the K4 was sent.

squeeze is checked as well as drawn: iambic B owes one element after a
released squeeze -- the element in progress finishes, and the opposite
of it follows -- and each run says whether it got it. A squeeze let go
of in the leading Dit Mem % of a dah and its gap is owed nothing.
dah-first and stall are checked too: a squeeze begins with the paddle
closed first, and a stall changes nothing about what is sent.
"""
import os, sys, importlib.util, types, queue, contextlib, threading, json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

MOD = sys.argv[1]
OUTDIR = sys.argv[2]
SCENARIO = sys.argv[3] if len(sys.argv) > 3 else 'tap'
assert SCENARIO in ('tap', 'dit-tap', 'swap', 'squeeze', 'dah-first',
                    'stall'), SCENARIO
SPEED = int(sys.argv[4]) if len(sys.argv) > 4 else 30
spec = importlib.util.spec_from_file_location('k4mod', MOD)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
if len(sys.argv) > 5:
    m.Keyer.set_dit_up_memory_delay_percent(float(sys.argv[5]))
DIT_MEM = m.Keyer.dit_up_memory_delay_percent

RATE, U = 48000, 384
BLOCK = U / RATE
WPM = SPEED
DIT = 1.2 / WPM                 # 40ms at 30 WPM
T0 = 100.1                      # when the first paddle closes

# Which paddle is closed at time zero and held -- None for squeeze,
# where both are -- how long it is held for, and the range the moment
# in question moves over. dit-tap runs further than the others because
# a dah is three times a dit: 80 to 300ms spans nearly five dah element
# periods, where 84 to 164 spans four dit ones. squeeze runs furthest,
# 4 to 500ms, which is two whole dit-gap-dah-gap cycles of the squeeze
# it is releasing and a little over, so the release falls in every part
# of one and the pattern is seen to repeat rather than assumed to.
HELD = {'tap': 'dit', 'dit-tap': 'dah', 'swap': 'dit',
        'squeeze': None, 'dah-first': 'dah', 'stall': 'dit'}[SCENARIO]
# squeeze has no held paddle -- both are let go at the moment being
# swept -- so its entry only has to carry the plots far enough right to
# show the element owed for the latest release, which ends at 544ms.
#
# dah-first sweeps the dit's closing from 4 to 40ms after the dah's,
# either side of the moment the first tone can be heard, which is where
# what the burst begins with is settled; both are let go of at 300ms.
#
# stall sweeps the moment the stall ends, from 200ms -- a stall too
# short to hold up anything the keyer does -- to 600, past the T's dah
# being closed at 400 and let go of at 460. Its HOLD only carries the
# plots far enough right to show the T keyed after the longest stall.
HOLD = {'tap': .400, 'dit-tap': .760, 'swap': .520,
        'squeeze': .500, 'dah-first': .300, 'stall': .680}[SCENARIO]
TAPS = {'tap': (84, 164), 'dit-tap': (80, 300), 'swap': (84, 164),
        'squeeze': (4, 500), 'dah-first': (4, 40),
        'stall': (200, 600)}[SCENARIO]
# Those are written for 30 WPM. At another speed they cover the same
# ground rather than the same milliseconds, the elements being what
# they are cut to: a dit at 40 WPM is three quarters of a dit at 30, so
# the sweep is three quarters as long. The step stays at 4ms, and the
# ends are moved to whole steps of it so that a run still lands on the
# moments the elements do. At 30 WPM nothing moves at all.
SCALE = 30 / WPM
if SCALE != 1:
    HOLD *= SCALE
    TAPS = (max(4, round(TAPS[0] * SCALE / 4) * 4),
            round(TAPS[1] * SCALE / 4) * 4)
WINDOW = HOLD + .12 * SCALE     # the plot's right edge, far enough past
                                # the last release to show the element
                                # owed for it, and scaled with the rest
MARK = {'dah': '#2b7bba', 'dit': '#c2410c', None: '#374151'}[HELD]
                                # the tapped paddle's colour, for the
                                # marker carried down the panels; a
                                # squeeze is let go of with both, so
                                # neither colour would be honest
HOP = .0001                     # device thread to keyer thread
LEAD = .016                     # how far ahead of its DAC time a block is filled
TIE_SECONDS = .000001           # a release landing on a tone's start;
                                # see squeeze_verdict

# stall: the S's dit is held from time zero to 200ms, which lets it go
# as its third dit ends, and the T's dah is closed at 400ms and let go
# of at 460. The process stalls from 190ms -- just before the dit is let
# go of -- until the moment swept: every paddle event the device sends
# in that time reaches the keyer at the end of it, a tenth of a
# millisecond apart, and the keyer's own thread is held too, waking a
# millisecond after them all. That is the order rc27_linux.txt came
# nearest to going wrong in: the reading after the S's last dit, woken
# late, with the whole of the T already standing. What the K4 should be
# told regardless is the S, a 200ms gap, and the T.
STALL_FROM = .190 * SCALE
STALL_PADDLES = [(0, 'dit_down'), (.200 * SCALE, 'dit_up'),
                 (.400 * SCALE, 'dah_down'), (.460 * SCALE, 'dah_up')]
STALL_GAP_MS = round(200 * SCALE)
MIDI_NOTE = {'dit': 20, 'dah': 21}


def sim(tap_at, tap_length=.005):
    clock = [100.0]
    A = m.Audio
    sent = []
    au = types.SimpleNamespace(
        key_event_queue=queue.SimpleQueue(), pending_key_event=None,
        sidetone_lag=0.0, sidetone_edge_shift=None, sidetone_schedule_offset=None,
        sidetone_down_asked=None, sidetone_down_placed=None,
        sidetone_down_cancelled=None, sidetone_down_dropped=None,
        sidetone_block_timing=None, block_lead_current=0.0,
        block_lead_previous=0.0, block_lead_window_end=None,
        block_lead_window_seconds=.5,
        output_stream_lock=contextlib.nullcontext(),
        report_audio_glitches=lambda during_sidetone=False: None)

    class Stream:
        @property
        def time(self):
            return clock[0] + 1000.0

    au.output_stream = Stream()
    au.peek_key_event = lambda: m.Audio.peek_key_event(au)
    au.key_edge_offset = lambda *a: m.Audio.key_edge_offset(au, *a)
    au.placed_sidetone_down = lambda: m.Audio.placed_sidetone_down(au)
    au.wanted_sidetone_lag = lambda: m.Audio.wanted_sidetone_lag(au)
    au.first_edge_lag = lambda: m.Audio.first_edge_lag(au)
    A.singleton = au
    A.sidetone_enabled = True
    A.minimum_sidetone_ms = 0
    A.report_glitches = classmethod(lambda cls, during_sidetone: None)

    # Where the speed and the delay together mean the paddles are read
    # before the element can be heard, the keyer says so. There is no
    # window here to say it in, and it is not what these runs are about.
    m.Popup.warning = classmethod(lambda cls, msg, **kw: None)

    grid0 = 1000.0 + 99.9
    st = dict(k=0, keyed=False, last_edge=-1e9)
    placed = []

    def sched(k):
        dac = grid0 + U * k / RATE
        return dac - LEAD, dac

    def callback(dac, cur):
        m.Audio.note_block_timing(au, dac, cur, BLOCK)
        if not st['keyed'] and au.pending_key_event is None and dac - st['last_edge'] > .5:
            au.sidetone_lag = 0.0
        start = 0
        while True:
            e = m.Audio.next_key_edge(au, start, U, dac, RATE)
            if e is None:
                break
            st['keyed'] = e[1]
            st['last_edge'] = dac + e[0] / RATE
            placed.append((dac + e[0] / RATE - 1000.0, e[1]))
            start = e[0]

    if SCENARIO == 'squeeze':
        # Both paddles closed at time zero and both let go together.
        script = [
            (T0, 'dit_down'),
            (T0, 'dah_down'),
            (T0 + tap_at, 'dit_up'),
            (T0 + tap_at, 'dah_up'),
        ]
    elif SCENARIO in ('tap', 'dit-tap'):
        # One paddle held throughout and the other tapped during it.
        tapped = 'dah' if HELD == 'dit' else 'dit'
        script = sorted([
            (T0, f'{HELD}_down'),
            (T0 + tap_at, f'{tapped}_down'),
            (T0 + tap_at + tap_length, f'{tapped}_up'),
            (T0 + HOLD, f'{HELD}_up'),
        ])
    elif SCENARIO == 'dah-first':
        # The dah closed first and the dit after it, both held, and both
        # let go of together.
        script = [
            (T0, 'dah_down'),
            (T0 + tap_at, 'dit_down'),
            (T0 + HOLD, 'dit_up'),
            (T0 + HOLD, 'dah_up'),
        ]
    elif SCENARIO == 'stall':
        script = [(T0 + when, what) for when, what in STALL_PADDLES]
    else:
        # The dit released and the dah closed in the same instant. The
        # dit's release is put first so the keyer sees the paddles in
        # the order the operator's hand made them.
        script = [
            (T0, 'dit_down'),
            (T0 + tap_at, 'dit_up'),
            (T0 + tap_at, 'dah_down'),
            (T0 + HOLD, 'dah_up'),
        ]
    # What reaches the keyer, and when: (arrival, event, when it
    # happened). Everywhere but a stall the two are the same instant.
    freeze = None
    if SCENARIO == 'stall':
        # Delivered in the order the device sent them, as a queue does:
        # what the stall held arrives from its end, a tenth of a
        # millisecond apart, and anything sent as it ends waits its turn
        # behind them.
        stall_from, stall_to = T0 + STALL_FROM, T0 + tap_at
        pending = []
        arrived = None
        held_until = None
        for when, what in script:
            at = stall_to if stall_from <= when < stall_to else when
            if arrived != None:
                at = max(at, arrived + .0001)
            if stall_from <= when < stall_to:
                held_until = at
            pending.append((at, what, when))
            arrived = at
        # The keyer's thread held from the stall's start until a
        # millisecond after the last held event reaches it.
        if held_until == None:
            held_until = stall_to
        freeze = (stall_from, held_until + .001)
    else:
        pending = [(when, what, when) for when, what in script]
    device_clock = [0.0]
    wake = [None]
    keyer = []

    def advance(to):
        while True:
            run, dac = sched(st['k'])
            run -= 1000.0
            nxt = min(run, pending[0][0] if pending else 1e18)
            if nxt > to:
                break
            clock[0] = max(clock[0], nxt)
            if pending and pending[0][0] == nxt:
                _, attr, happened = pending.pop(0)
                k = keyer[0]
                if SCENARIO == 'stall':
                    send_midi(k, attr, happened)
                else:
                    k.send_paddle_event(getattr(k, attr.upper() + '_EVENT'), 0)
                if wake[0] is None:
                    wake[0] = clock[0] + HOP
            else:
                callback(dac, run + 1000.0)
                st['k'] += 1
        clock[0] = max(clock[0], to)

    def send_midi(k, attr, happened):
        # As a MoMIDI device sends it: the time since its last event in
        # 126ms steps by polyphonic aftertouch, where there are any, and
        # the milliseconds left over as the note's velocity -- never 0
        # or 127, which say there is no time in it at all.
        delta = happened - device_clock[0]
        device_clock[0] = happened
        steps = int(delta / .126)
        ms = max(1, min(126, round((delta - steps * .126) * 1000)))
        side, edge = attr.split('_')
        note = MIDI_NOTE[side]
        if steps:
            k.midi_message_callback(((0xa0, note, steps), 0))
        k.midi_message_callback((((0x90 if edge == 'down' else 0x80),
                                  note, ms), 0))

    class T:
        perf_counter = staticmethod(lambda: clock[0])

        @staticmethod
        def sleep(s):
            # The keyer's thread, held for as long as a stall lasts.
            to = clock[0] + s
            if freeze != None and freeze[0] <= to < freeze[1]:
                to = freeze[1]
            advance(to)

    m.time = T
    m.dprint1 = lambda *a, **k: None

    class S:
        def send_str(self, s):
            sent.append((clock[0] - T0, s))
            advance(clock[0] + .0002)

        def k4_parameter(self, p):
            return str(WPM) if p == 'KS' else '0'

        def subscribe_received_initial_parameters(self, cb):
            pass

        def subscribe_response(self, cmd, cb):
            pass

        def unsubscribe_response(self, cmd, cb):
            pass

    class Set:
        def getbool(self, s, k, d):
            return False

        def getfloat(self, s, k, d):
            return d

    m.Server.k4_server, m.Server.settings = S(), Set()
    # The keyer's threads stand still here: this runs the keyer's own
    # work inline on a virtual clock. The timer that puts the K4's
    # sidetone monitor back after a burst is inert for the same reason
    # -- a real one would fire on the wall clock, in the middle of a run
    # that has not reached that instant yet.
    m.threading = types.SimpleNamespace(
        Thread=lambda **kw: types.SimpleNamespace(start=lambda: None),
        Timer=lambda *a, **kw: types.SimpleNamespace(start=lambda: None,
                                                     cancel=lambda: None),
        Lock=threading.Lock)
    m.Keyer.straight_keying = False
    m.Keyer.dit_paddle_notes = [MIDI_NOTE['dit']]
    m.Keyer.dah_paddle_notes = [MIDI_NOTE['dah']]
    m.Keyer.keyer_mode = m.Keyer.MODE_IAMBIC_B
    k = m.Keyer()
    keyer.append(k)
    k.keyer_mode = m.Keyer.MODE_IAMBIC_B
    k.on_speed_change()

    end = T0 + WINDOW + .4
    while clock[0] < end:
        nxt = wake[0] if wake[0] is not None else (
            pending[0][0] if pending else end)
        advance(min(nxt, end))
        if wake[0] is not None and clock[0] >= wake[0]:
            wake[0] = None
            if not k.paddle_event_queue.empty():
                k.send_iambic()
                if not k.paddle_event_queue.empty():
                    wake[0] = clock[0]

    return dict(
        script=[(t - T0, what) for t, what in script],
        edges=[(t - T0, down) for t, down in placed],
        sent=sent,
        dit_seconds=k.dit_seconds,
        dah_seconds=k.dah_seconds,
        # The Dit Mem window, reckoned as send_iambic reckons it.
        dit_mem_seconds=(DIT_MEM / 100 *
                         (k.dah_seconds + k.inter_element_seconds)),
    )


def elements_from(sent):
    # Each KZU carries the element's length, so the tones can be named.
    out = []
    for when, cmd in sent:
        if cmd.startswith('KZU'):
            ms = int(cmd[3:7])
            out.append('dah' if ms > round(DIT * 1000 * 2) else 'dit')
    return out


def squeeze_verdict(result, release_at):
    # What iambic B owes for a released squeeze: exactly one more
    # element, the opposite of the one the squeeze was let go of during,
    # and nothing after it -- or, let go of in a dah's Dit Mem window,
    # nothing at all.
    #
    # The rule is about what the operator could hear, so the windows are
    # cut from the sidetone as the output callback really placed it and
    # not from the keyed grid -- the two are a lag apart, and a release
    # can fall after an element was keyed but before any of it was
    # audible. A window is a tone and the space following it, up to the
    # next tone starting, so every release falls in exactly one.
    #
    # A release before the first tone can be heard belongs to the first
    # window. That element the operator began themselves by closing the
    # paddle, so letting go before it could be heard is still letting go
    # during it.
    #
    # A release landing on a tone's start belongs to both windows and to
    # neither. The step is a whole number of milliseconds and so are the
    # elements, so at some speeds a run puts the release on a tone's
    # start exactly -- at 40 WPM the release at 204ms is the third tone's
    # start to the last bit. The rule has nothing to say about that
    # instant: the space of the window before has just run out and the
    # tone of the window after has not yet been heard for any length of
    # time at all. Which side of it a run comes down on is settled by
    # which way a subtraction rounded, here and in the keyer separately,
    # and the two need not agree -- they are the same quantity reached
    # by different routes, a stream clock and a paddle clock apart.
    #
    # So both readings are honoured, and a run passes on either. The
    # width below is a thousand times finer than anything the keying
    # turns on and fifty times finer than the frame an edge is placed
    # on, but a hundred million times the rounding. Nothing that is
    # really wrong is wrong by a microsecond: a squeeze that earns the
    # wrong number of elements earns a whole one too many or too few.
    #
    # Returns (the element released during, what is owed, what followed,
    # whether the rule was met).
    elements = elements_from(result['sent'])
    heard = [when for when, down in result['edges'] if down]
    if not elements or not heard:
        return None, None, [], False
    count = min(len(heard), len(elements))
    window = 0
    for index in range(count):
        if release_at > heard[index] + TIE_SECONDS:
            window = index
    windows = [window]
    if window + 1 < count and release_at > heard[window + 1] - TIE_SECONDS:
        windows.append(window + 1)

    # What a release in a window may be owed: the opposite element, or
    # 'nothing' for a dah let go of inside the Dit Mem window -- the
    # leading Dit Mem % of the dah and its gap, from when the dah was
    # heard, which is where send_iambic measures a released squeeze
    # from. The window's edge is a tie like a tone's start, and for the
    # same reason allowed either answer.
    def owed_by(index):
        if elements[index] == 'dit':
            return ['dah']
        into = release_at - heard[index]
        delay = result['dit_mem_seconds']
        if into > delay + TIE_SECONDS:
            return ['dit']
        if into < delay - TIE_SECONDS:
            return ['nothing']
        return ['dit', 'nothing']

    for index in windows:
        for owed in owed_by(index):
            wanted = [] if owed == 'nothing' else [owed]
            if elements[index + 1:] == wanted:
                return elements[index], owed, elements[index + 1:], True
    return (elements[window], owed_by(window)[0], elements[window + 1:],
            False)


def dah_first_verdict(result, dit_at):
    # A squeeze begins with the paddle closed first and alternates from
    # there: dah, dit, dah and so on, for as long as it is held. Returns
    # (what was sent, whether it did).
    elements = elements_from(result['sent'])
    alternating = all(a != b for a, b in zip(elements, elements[1:]))
    return elements, bool(elements) and elements[0] == 'dah' and alternating


def stall_verdict(result):
    # The S, the gap the operator left, and the T, whatever the stall:
    # nothing added, nothing lost, nothing run together. Returns (the
    # gap the T's KZD carried, whether all of that held).
    elements = elements_from(result['sent'])
    kzds = [cmd for _, cmd in result['sent'] if cmd.startswith('KZD')]
    gap = kzds[3] if len(kzds) > 3 else None
    met = (elements == ['dit', 'dit', 'dit', 'dah'] and
           gap == f'KZD{STALL_GAP_MS:04d};')
    return gap, met


def plot(result, tap_at, path):
    fig, axes = plt.subplots(3, 1, figsize=(13, 6.6), sharex=True,
                             gridspec_kw=dict(height_ratios=[2, 1.9, 1.7]))
    fig.subplots_adjust(hspace=.2, left=.085, right=.985, top=.88, bottom=.09)
    xmax = WINDOW * 1000
    for ax in axes:
        ax.set_axisbelow(True)          # bars over the grid, not under it
        # Where the tap landed, carried down all three panels, in the
        # colour of the paddle that made it.
        ax.axvline(tap_at * 1000, color=MARK, lw=1, ls=(0, (4, 3)),
                   alpha=.55, zorder=1)
        if SCENARIO == 'stall':
            # The stall, shaded down all three panels.
            ax.axvspan(STALL_FROM * 1000, tap_at * 1000, color='#9ca3af',
                       alpha=.14, lw=0, zorder=0)

    # What the operator did.
    ax = axes[0]
    spans = {'dit': [], 'dah': []}
    open_at = {}
    for when, what in result['script']:
        side, edge = what.split('_')
        if edge == 'down':
            open_at[side] = when
        else:
            spans[side].append((open_at.pop(side), when))
    for side in ('dit', 'dah'):
        if side in open_at:
            spans[side].append((open_at[side], WINDOW))
    for row, (side, colour) in enumerate((('dit', '#2b7bba'), ('dah', '#c2410c'))):
        for start, stop in spans[side]:
            ax.add_patch(Rectangle((start * 1000, row + .12),
                                   max((stop - start) * 1000, .8), .76,
                                   facecolor=colour, edgecolor=colour))
    ax.set_yticks([.5, 1.5])
    ax.set_yticklabels(['dit paddle', 'dah paddle'])
    ax.set_ylim(0, 2)
    what = {
        'tap': 'dit paddle held, dah paddle tapped for 5 ms',
        'dit-tap': 'dah paddle held, dit paddle tapped for 5 ms',
        'swap': 'dit paddle released and dah paddle closed',
        'squeeze': 'both paddles squeezed, both released',
        'dah-first': 'dah paddle closed, dit paddle closed',
        'stall': (f'S then T over MIDI, the process stalled from '
                  f'{STALL_FROM * 1000:.0f} ms to'),
    }[SCENARIO]
    joiner = ' ' if SCENARIO == 'stall' else ' at '
    ax.set_title(f'{WPM} WPM iambic B — {what}{joiner}{tap_at * 1000:.0f} ms',
                 fontsize=12.5, pad=16)
    ax.text(tap_at * 1000, 2.06, f'{tap_at * 1000:.0f} ms', ha='center',
            va='bottom', fontsize=9.5, color=MARK, weight='bold')

    # What the operator heard. Each tone is filled and named, so a dit
    # can be told from a dah at a glance, with its length beside it.
    ax = axes[1]
    names = elements_from(result['sent'])
    level, last = 0, 0.0
    steps_x, steps_y = [0.0], [0]
    tones = []
    for when, down in result['edges']:
        steps_x += [when * 1000, when * 1000]
        steps_y += [level, 1 - level]
        if not down:
            tones.append((last, when))
        level, last = 1 - level, when
    steps_x.append(xmax)
    steps_y.append(level)
    ax.plot(steps_x, steps_y, color='#166534', lw=2, zorder=3)
    for index, (start, stop) in enumerate(tones):
        ax.add_patch(Rectangle((start * 1000, 0), (stop - start) * 1000, 1,
                               facecolor='#166534', alpha=.16, lw=0, zorder=2))
        name = names[index] if index < len(names) else '?'
        ax.text((start + stop) / 2 * 1000, 1.36, name, ha='center',
                va='center', fontsize=11.5, color='#166534', weight='bold')
        ax.text((start + stop) / 2 * 1000, 1.72,
                f'{(stop - start) * 1000:.0f} ms', ha='center', va='center',
                fontsize=7.5, color='#166534')
    ax.set_yticks([0, 1])
    ax.set_yticklabels(['off', 'on'])
    ax.set_ylim(-.3, 2.0)
    ax.set_ylabel('sidetone', fontsize=10)

    # What the K4 was sent. Key down above the line, key up below, so
    # the labels of a closely spaced pair do not sit on top of each other.
    #
    # The key commands alone. A burst also mutes the K4's own sidetone
    # monitor as it begins and puts it back when it ends, and that is
    # not a key edge: drawn here it would hang below the line looking
    # like one.
    ax = axes[2]
    ax.axhline(0, color='#d1d5db', lw=.8)
    for when, cmd in result['sent']:
        if not cmd.startswith(('KZD', 'KZU')):
            continue
        down = cmd.startswith('KZD')
        colour = '#6d28d9' if down else '#a78bfa'
        y = .62 if down else -.62
        ax.plot([when * 1000, when * 1000], [0, y], color=colour, lw=1.3)
        ax.plot([when * 1000], [y], 'o', color=colour, ms=4)
        ax.text(when * 1000, y + (.16 if down else -.16), cmd.rstrip(';'),
                fontsize=7.5, ha='center',
                va='bottom' if down else 'top', color=colour)
    ax.set_ylim(-1.35, 1.35)
    ax.set_yticks([])
    ax.set_ylabel('K4 commands', fontsize=10)
    ax.set_xlabel('milliseconds after both paddles closed' if HELD == None
                  else f'milliseconds after the {HELD} paddle closed',
                  fontsize=10)

    for ax in axes:
        ax.set_xlim(-8, xmax)
        ax.grid(axis='x', color='#e5e7eb', lw=.6)
        for spine in ('top', 'right'):
            ax.spines[spine].set_visible(False)

    fig.savefig(path, dpi=110)
    plt.close(fig)


os.makedirs(OUTDIR, exist_ok=True)
summary = []
owed_total = owed_met = 0
for tap_ms in range(TAPS[0], TAPS[1] + 1, 4):
    tap_at = tap_ms / 1000
    result = sim(tap_at)
    path = os.path.join(
        OUTDIR, f'keying_{WPM}wpm_{SCENARIO}_{tap_ms:03d}ms.png')
    plot(result, tap_at, path)
    elements = ' '.join(elements_from(result['sent']))
    entry = dict(tap_ms=tap_ms, elements=elements,
                 sent=[c for _, c in result['sent']],
                 edges=len(result['edges']))
    verdict = ''
    if SCENARIO == 'squeeze':
        during, owed, after, met = squeeze_verdict(result, tap_at)
        entry.update(released_during=during, owed=owed,
                     followed=' '.join(after))
        if owed == None:
            verdict = '  nothing sent'
        else:
            owed_total += 1
            if met:
                owed_met += 1
                if owed == 'nothing':
                    verdict = (f'  released during the {during} inside Dit '
                               f'Mem, nothing owed and nothing sent')
                else:
                    verdict = (f'  released during the {during}, {owed} '
                               f'owed and sent')
            else:
                verdict = (f'  WRONG: released during the {during}, {owed} '
                           f'owed, got {" ".join(after) or "nothing"}')
    elif SCENARIO == 'dah-first':
        sent_elements, met = dah_first_verdict(result, tap_at)
        entry.update(met=met)
        owed_total += 1
        if met:
            owed_met += 1
            verdict = '  begun with the dah, alternating'
        else:
            verdict = '  WRONG: not begun with the dah, or not alternating'
    elif SCENARIO == 'stall':
        gap, met = stall_verdict(result)
        entry.update(gap=gap, met=met)
        owed_total += 1
        if met:
            owed_met += 1
            verdict = f'  S, {gap.rstrip(";")}, T'
        else:
            verdict = (f'  WRONG: wanted S, KZD{STALL_GAP_MS:04d}, T; '
                       f'the T\'s KZD was {gap}')
    summary.append(entry)
    print(f'{tap_ms:3d} ms  {elements:24s}  {len(result["edges"]):2d} sidetone edges  '
          f'-> {os.path.basename(path)}{verdict}')

if SCENARIO == 'dah-first':
    print(f'\n{owed_met}/{owed_total} squeezes begun with the dah closed '
          f'first began with it and alternated')
if SCENARIO == 'stall':
    print(f'\n{owed_met}/{owed_total} stalls left the S, the '
          f'{STALL_GAP_MS}ms gap and the T as the operator sent them')
if SCENARIO == 'squeeze':
    print(f'\n{owed_met}/{owed_total} releases got what iambic B owes them '
          f'-- one element, or none inside Dit Mem {DIT_MEM:g}% -- and '
          f'nothing after it')

json.dump(summary,
          open(os.path.join(OUTDIR, f'summary_{WPM}wpm_{SCENARIO}.json'), 'w'),
          indent=1)
