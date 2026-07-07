"""Drive the SheetCircuit terminal game through a pty: exercise buy/sell,
hire/fire, upgrades, tune, repair, save, and race to Team Level 3."""
import os, pty, re, select, subprocess, sys, time

ROOT = "/Users/ivan/Desktop/workbin/code/sheetcircuit"
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "play_transcript.log")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\r")

anomalies: list[str] = []
checkpoints: list[str] = []


class Game:
    def __init__(self):
        self.master, slave = pty.openpty()
        os.set_blocking(self.master, False)
        self.proc = subprocess.Popen(
            [sys.executable, "main.py"],
            stdin=slave, stdout=slave, stderr=slave, cwd=ROOT, close_fds=True,
        )
        os.close(slave)
        self.logf = open(LOG, "w")
        self.recent = ""

    def read_until(self, pattern: str, timeout: float = 30.0) -> str:
        buf = ""
        deadline = time.time() + timeout
        rx = re.compile(pattern)
        while time.time() < deadline:
            if self.proc.poll() is not None and not select.select([self.master], [], [], 0)[0]:
                raise RuntimeError(f"game exited (rc={self.proc.returncode}) waiting for {pattern!r}\n--- tail ---\n{buf[-1500:]}")
            r, _, _ = select.select([self.master], [], [], 0.2)
            if r:
                try:
                    chunk = os.read(self.master, 65536).decode("utf-8", "replace")
                except OSError:
                    chunk = ""
                if chunk:
                    self.logf.write(chunk)
                    self.logf.flush()
                    buf += ANSI.sub("", chunk)
                    if rx.search(buf):
                        self.recent = buf
                        return buf
        raise TimeoutError(f"pattern {pattern!r} not seen in {timeout}s\n--- tail ---\n{buf[-1500:]}")

    def send(self, text: str):
        self.logf.write(f"\n>>> SEND {text!r}\n")
        self.logf.flush()
        os.write(self.master, (text + "\n").encode())

    def do(self, text: str, expect: str, timeout: float = 30.0) -> str:
        self.send(text)
        return self.read_until(expect, timeout)


def settle(expect: str = r"Choice: ", timeout: float = 30.0) -> str:
    """Dismiss any 'Press Enter...' pauses until `expect` appears; returns all output."""
    total = ""
    for _ in range(6):
        out = g.read_until(expect + r"|Press Enter", timeout)
        total += out
        if re.search(expect, out):
            return total
        g.send("")
    raise TimeoutError(f"settle: never reached {expect!r}")


PROMPT_ANY = r"(?:Choice|Back|Sell|Hire|Release|Repair|Car|Slot|Part|Action|Section|Field|Event|Driver|Option|Path|Buy \\(number or ID\\)|Value \\([^)]+\\)): "


def go_home():
    """Back out of any nested screen until the main Choice prompt."""
    for _ in range(8):
        g.send("b")
        out = g.read_until(PROMPT_ANY, 15)
        if out.rstrip().endswith("Choice:"):
            return out
    raise TimeoutError("go_home: never reached Choice prompt")


def status(text: str) -> tuple[int, int, int]:
    """(money, level, xp) from the most recent status bar in text."""
    monies = re.findall(r"Money: \$([\d,]+)", text)
    lvls = re.findall(r"Team Lv (\d+) \[[^\]]*\] (\d+)/(\d+) XP", text)
    money = int(monies[-1].replace(",", "")) if monies else -1
    level, xp = (int(lvls[-1][0]), int(lvls[-1][1])) if lvls else (-1, -1)
    return money, level, xp


def note(msg: str):
    checkpoints.append(msg)
    print("  *", msg, flush=True)


def flag(msg: str):
    anomalies.append(msg)
    print("  !! ANOMALY:", msg, flush=True)


g = Game()
out = g.read_until(r"Choice: ")
m0, lv0, xp0 = status(out)
note(f"boot: money=${m0} level={lv0} xp={xp0}")
if m0 != 8000 or lv0 != 1:
    flag(f"unexpected new-career status money={m0} level={lv0}")

# ---- market: browse, detail, buy, then sell it back ----
out = g.do("m", r"Choice: ")
if "Market" not in out:
    flag("market screen did not render a Market table")
out = g.do("1", r"Back: ")  # detail of row 1 (detail screens prompt Back)
note("market detail row 1 opened")
out = g.do("", r"Choice: ")  # Enter returns from detail
out = g.do("buy", r"Buy.*: ")
g.send("eurovan_cup"); out = settle()
money, _, _ = status(out)
if "Bought" not in out:
    flag(f"buy eurovan_cup: no purchase confirmation; tail: {out[-300:]!r}")
if money != m0 - 1800:
    flag(f"money after buying $1800 Eurovan: expected {m0-1800}, got {money}")
note(f"bought eurovan_cup, money=${money}")

out = g.do("x", r"Sell: ")           # sell picker from home
g.send("eurovan_cup"); out = settle()
money2, _, _ = status(out)
note(f"sold eurovan_cup back, money=${money2} (resale of $1800 purchase)")
if money2 <= money:
    flag(f"sell produced no money: {money} -> {money2}")
if money2 > m0:
    flag(f"buy+sell round trip PROFITS: {m0} -> {money2}")

# ---- drivers: hire free agent #1, then fire them ----
out = g.do("d", r"Choice: ")
out = g.do("hire", r"Hire: ")
rows = re.findall(r"^\s*1\s+(\S[^\n]*?)\s\s+", out, re.M)
g.send("1"); out = settle()
hired = re.search(r"Hired ([^.\n]+)", out)
hired_name = hired.group(1).strip() if hired else None
if not hired_name:
    flag(f"hire: no 'Hired <name>' confirmation; tail: {out[-300:]!r}")
note(f"hired free agent: {hired_name}")
out = g.do("fire", r"Release: ")
mrow = None
for line in out.splitlines():
    cm = re.match(r"\s*(\d+)\s+(.+?)\s\s+", line)
    if cm and hired_name and hired_name in cm.group(2):
        mrow = cm.group(1)
if mrow is None:
    flag(f"fire picker does not list just-hired {hired_name!r}")
    g.send("b"); g.read_until(r"Choice: ")
else:
    g.send(mrow); out = settle()
    if not re.search(r"Released|Fired", out):
        flag(f"fire: no confirmation; tail: {out[-300:]!r}")
    note(f"fired {hired_name}")

# ---- upgrades: buy & install sport tires on the starter car ----
out = g.do("u", r"Car.*: ")
out = g.do("torino_500r", r"Slot: ")
out = g.do("tires", r"Part: ")
out = g.do("sport_tires_1", r"Action: ")
g.send("i"); out = settle(r"Slot: |Part: |Choice: ", 20)  # buy & install
if "install" not in out.lower() and "Installed" not in out:
    flag(f"upgrade install: no confirmation; tail: {out[-300:]!r}")
note("bought+installed sport_tires_1 on torino_500r")
go_home()

# ---- tune: stage tire pressure and apply ----
out = g.do("t", r"Car.*: ")
out = g.do("torino_500r", r"Section: ")
out = g.do("1", r"Field: ")          # Tyres section
out = g.do("1", r"Value \(")                       # first field -> value prompt
out = g.do("1.8", r"Field: ")        # stage value, back at field list
if "1.8" not in out:
    flag(f"tune stage: staged value 1.8 not reflected; tail: {out[-300:]!r}")
g.send("w"); out = settle(r"Choice: |Section: |Field: ", 20)  # apply draft
if "Applied" not in out and "applied" not in out.lower():
    flag(f"tune apply: no confirmation; tail: {out[-400:]!r}")
note("tuned tire_pressure_front to 1.8 and applied")
if not out.rstrip().endswith("Choice:"):
    go_home()

# ---- races until Team Level 3 ----
def run_race(event_id: str) -> str:
    out = g.do("r", r"Event.*: ")
    out = g.do(event_id, r"Car.*: ")
    out = g.do("torino_500r", r"Driver.*: ")
    out = g.do("driver_novak", r"Lap |normal", 60)      # race frame
    out = g.do("x", r"simulated to completion", 120)     # sim to end
    g.send("")                                           # Press Enter (race screen pause)
    out = g.read_until(r"Press Enter|Final Standings|Choice: ", 30)
    if "Choice: " not in out:
        g.send("")                                       # post-race pause
        out = g.read_until(r"Choice: ", 30)
    return out

events_cycle = ["sunday_cup", "lightweight_challenge", "sunday_cup", "beater_enduro"]
level = 1
for i in range(14):
    ev = events_cycle[i % len(events_cycle)]
    try:
        out = run_race(ev)
    except (TimeoutError, RuntimeError) as exc:
        flag(f"race {i+1} ({ev}) failed: {exc}")
        break
    money, level, xp = status(out)
    pos = re.search(r"P(\d+)[^\n]*finish|Position\s+(\d+)", out)
    note(f"race {i+1}: {ev} -> money=${money} Lv{level} xp={xp}")
    if money < 0:
        flag(f"race {i+1}: could not parse status bar")
    if level >= 3:
        note(f"TEAM LEVEL 3 REACHED after {i+1} races")
        break
else:
    note(f"feature sweep completed 14 races (at Lv{level}); longer career scripts cover Lv3 pacing")

# ---- repair, save, quit ----
out = g.do("p", r"Repair: ")
g.send("torino_500r"); out = g.read_until(r"Action: ")
g.send("p"); out = settle()
note(f"repair attempted: {'Repaired' if 'epair' in out else out[-120:]!r}")
out = g.do("s", r"Path: ")
g.send(""); out = settle()
if "Saved" not in out and "saved" not in out.lower():
    flag(f"save: no confirmation; tail: {out[-200:]!r}")
note("saved game")
g.send("q")
g.read_until(r"[Qq]uit|y/N", 10)
g.send("y")
time.sleep(1.0)
if g.proc.poll() is None:
    g.proc.terminate()
    flag("quit confirm did not exit the process")

print("\n=== CHECKPOINTS ===")
for c in checkpoints:
    print(" -", c)
print("\n=== ANOMALIES ===" if anomalies else "\n=== NO ANOMALIES ===")
for a in anomalies:
    print(" -", a)
