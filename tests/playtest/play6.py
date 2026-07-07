"""Session 4: load the session-3 save through the UI and finish the run to Team Lv3."""
import os, pty, re, select, subprocess, sys, time

ROOT = "/Users/ivan/Desktop/workbin/code/sheetcircuit"
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "play6_transcript.log")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\r")
anomalies, checkpoints = [], []


class Game:
    def __init__(self):
        self.master, slave = pty.openpty()
        os.set_blocking(self.master, False)
        self.proc = subprocess.Popen([sys.executable, "main.py"], stdin=slave, stdout=slave, stderr=slave, cwd=ROOT, close_fds=True)
        os.close(slave)
        self.logf = open(LOG, "w")

    def read_until(self, pattern, timeout=30.0):
        buf, deadline, rx = "", time.time() + timeout, re.compile(pattern)
        while time.time() < deadline:
            if self.proc.poll() is not None and not select.select([self.master], [], [], 0)[0]:
                raise RuntimeError(f"game exited rc={self.proc.returncode} waiting {pattern!r}\n{buf[-1200:]}")
            r, _, _ = select.select([self.master], [], [], 0.2)
            if r:
                try:
                    chunk = os.read(self.master, 65536).decode("utf-8", "replace")
                except OSError:
                    chunk = ""
                if chunk:
                    self.logf.write(chunk); self.logf.flush()
                    buf += ANSI.sub("", chunk)
                    if rx.search(buf):
                        return buf
        raise TimeoutError(f"{pattern!r} not seen in {timeout}s\n--- tail ---\n{buf[-1200:]}")

    def send(self, text):
        self.logf.write(f"\n>>> SEND {text!r}\n"); self.logf.flush()
        os.write(self.master, (text + "\n").encode())

    def do(self, text, expect, timeout=30.0):
        self.send(text)
        return self.read_until(expect, timeout)


def settle(expect=r"Choice: ", timeout=30.0):
    total = ""
    for _ in range(6):
        out = g.read_until(expect + r"|Press Enter", timeout)
        total += out
        if re.search(expect, out):
            return total
        g.send("")
    raise TimeoutError(f"settle: never reached {expect!r}")


def status(text):
    monies = re.findall(r"Money: \$([\d,]+)", text)
    lvls = re.findall(r"Team Lv (\d+) \[[^\]]*\] (\d+)/(\d+) XP", text)
    money = int(monies[-1].replace(",", "")) if monies else -1
    level, xp = (int(lvls[-1][0]), int(lvls[-1][1])) if lvls else (-1, -1)
    return money, level, xp


def note(msg):
    checkpoints.append(msg); print("  *", msg, flush=True)


def flag(msg):
    anomalies.append(msg); print("  !! ANOMALY:", msg, flush=True)


g = Game()
g.read_until(r"Choice: ")

# load session-3 save through the UI
out = g.do("l", r"Path: ")
g.send("saves/save1.json"); out = settle()
money, level, xp = status(out)
note(f"loaded save: ${money} Lv{level} {xp}xp")


def run_race(event_id, car_id):
    out = g.do("r", r"Event: ")
    out = g.do(event_id, r"Car: ")
    out = g.do(car_id, r"Driver: ")
    out = g.do("driver_novak", r"Lap |command|exceeds|Press Enter", 60)
    if "exceeds" in out or "Press Enter" in out:
        g.send("")
        settle()
        raise ValueError(f"entry rejected: {out[-200:]}")
    out = g.do("x", r"simulated to completion", 180)
    g.send("")
    out2 = g.read_until(r"Press Enter|Choice: ", 30)
    if "Choice: " not in out2:
        g.send("")
        out2 += g.read_until(r"Choice: ", 30)
    return out + out2


def repair(car_id):
    out = g.do("p", r"Repair: ")
    g.send(car_id); out = g.read_until(r"Action: ")
    g.send("f"); out = settle()
    if "Insufficient" in out:
        note(f"repair {car_id}: insufficient funds (skipped)")
    return out


races, phase = 0, "farm"
fresh = ["beater_enduro", "lightweight_challenge", "beater_enduro", "lightweight_challenge", "beater_enduro"]
for i in range(30):
    if phase == "farm" and money >= 900:
        phase = "fresh"
        note("farm done, switching to never-entered E events with the Torino")
    if phase == "fresh":
        ev, car = fresh[min(races % 5, 4)] if False else (fresh.pop(0) if fresh else ("sunday_cup",)), "torino_500r"
        ev = ev[0] if isinstance(ev, tuple) else ev
        if not fresh:
            fresh = ["beater_enduro", "lightweight_challenge"]
    else:
        ev, car = "open_track_day", "eurovan_cup"
    try:
        out = run_race(ev, car)
    except ValueError as exc:
        flag(str(exc)); break
    except (TimeoutError, RuntimeError) as exc:
        flag(f"race {i+1} ({ev}) failed: {exc}"); break
    races += 1
    money, level, xp = status(out)
    prize = re.search(r"Prize: \$(\d+)", out)
    teamxp = re.search(r"Team XP\s+\+(\d+)", out)
    conds = re.findall(r"Overall\s+(\d+(?:\.\d+)?)%", out)
    condition = float(conds[-1]) if conds else -1
    note(f"race {races}: {ev} [{car}] prize=${prize.group(1) if prize else '?'} +{teamxp.group(1) if teamxp else '0'}xp -> ${money} Lv{level} {xp}xp cond={condition}%")
    if level >= 3:
        note(f"*** TEAM LEVEL 3 REACHED after {races} races this session ***")
        break
    if money < 120:
        flag(f"broke: ${money}")
        break
else:
    flag(f"did not reach Lv3 in {races} more races")

# save the finished career via /save palette (instant, no path prompt) and quit
out = g.do("/save", r"Saved", 15)
g.send("")
g.read_until(r"Choice: ", 15)
note("palette /save issued")
g.send("q")
g.read_until(r"\[y/N\]:", 10)
g.send("y")
time.sleep(1.0)
if g.proc.poll() is None:
    g.proc.terminate()
    flag("quit did not exit process")

print("\n=== CHECKPOINTS ===")
for c in checkpoints: print(" -", c)
print("\n=== ANOMALIES ===" if anomalies else "\n=== NO ANOMALIES ===")
for a in anomalies: print(" -", a)
