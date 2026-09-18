"""A sweep of keying simulations, at 30 WPM unless told otherwise.

Four scenarios, chosen by the third argument, and a speed in words a
minute by an optional fourth:

  tap      the dit paddle is held closed throughout and the dah paddle
           is tapped for 5ms
  dit-tap  the mirror of it: the dah paddle held and the dit tapped
  swap     the dit paddle is released at the same instant the dah
           paddle is closed, and the dah is then held
  squeeze  both paddles closed at time zero and both let go together

The moment in question moves 4ms per run. Each run drives the real
Keyer over a virtual clock and writes a plot of what the operator did,
what they heard, and what the K4 was sent.

squeeze is checked as well as drawn: iambic B owes one element after a
released squeeze -- the element in progress finishes, and the opposite
of it follows -- and each run says whether it got it.
"""
import os, sys, importlib.util, types, queue, contextlib, threading, json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

MOD = sys.argv[1]
OUTDIR = sys.argv[2]
SCENARIO = sys.argv[3] if len(sys.argv) > 3 else 'tap'
assert SCENARIO in ('tap', 'dit-tap', 'swap', 'squeeze'), SCENARIO
SPEED = int(sys.argv[4]) if len(sys.argv) > 4 else 30
spec = importlib.util.spec_from_file_location('k4mod', MOD)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

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
        'squeeze': None}[SCENARIO]
# squeeze has no held paddle -- both are let go at the moment being
# swept -- so its entry only has to carry the plots far enough right to
# show the element owed for the latest release, which ends at 544ms.
HOLD = {'tap': .400, 'dit-tap': .760, 'swap': .520,
        'squeeze': .500}[SCENARIO]
TAPS = {'tap': (84, 164), 'dit-tap': (80, 300), 'swap': (84, 164),
        'squeeze': (4, 500)}[SCENARIO]
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
    A.singleton = au
    A.sidetone_enabled = True
    A.minimum_sidetone_ms = 0
    A.mute_k4 = classmethod(lambda cls, unmute_after=None: None)
    A.report_glitches = classmethod(lambda cls, during_sidetone: None)

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
    pending = list(script)
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
                _, attr = pending.pop(0)
                k = keyer[0]
                k.send_paddle_event(getattr(k, attr.upper() + '_EVENT'), 0)
                if wake[0] is None:
                    wake[0] = clock[0] + HOP
            else:
                callback(dac, run + 1000.0)
                st['k'] += 1
        clock[0] = max(clock[0], to)

    class T:
        perf_counter = staticmethod(lambda: clock[0])

        @staticmethod
        def sleep(s):
            advance(clock[0] + s)

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

    class Set:
        def getbool(self, s, k, d):
            return False

        def getfloat(self, s, k, d):
            return d

    m.Server.k4_server, m.Server.settings = S(), Set()
    m.threading = types.SimpleNamespace(
        Thread=lambda **kw: types.SimpleNamespace(start=lambda: None),
        Lock=threading.Lock)
    m.Keyer.saved_inherent_sidetone_lag = lambda self: .016
    m.Keyer.straight_keying = False
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
    # and nothing after it.
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

    owed_by = lambda index: 'dit' if elements[index] == 'dah' else 'dah'
    for index in windows:
        if elements[index + 1:] == [owed_by(index)]:
            return elements[index], owed_by(index), elements[index + 1:], True
    return (elements[window], owed_by(window), elements[window + 1:], False)


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
    }[SCENARIO]
    ax.set_title(f'{WPM} WPM iambic B — {what} at {tap_at * 1000:.0f} ms',
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
    ax = axes[2]
    ax.axhline(0, color='#d1d5db', lw=.8)
    for when, cmd in result['sent']:
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
                verdict = f'  released during the {during}, {owed} owed and sent'
            else:
                verdict = (f'  WRONG: released during the {during}, {owed} '
                           f'owed, got {" ".join(after) or "nothing"}')
    summary.append(entry)
    print(f'{tap_ms:3d} ms  {elements:24s}  {len(result["edges"]):2d} sidetone edges  '
          f'-> {os.path.basename(path)}{verdict}')

if SCENARIO == 'squeeze':
    print(f'\n{owed_met}/{owed_total} releases got the one element iambic B '
          f'owes them, and nothing after it')

json.dump(summary,
          open(os.path.join(OUTDIR, f'summary_{WPM}wpm_{SCENARIO}.json'), 'w'),
          indent=1)
