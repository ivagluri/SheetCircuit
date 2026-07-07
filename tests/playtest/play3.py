"""Session 2: play a *smart* career to Team Level 3 — better car, repair
discipline, D-class events once unlocked. Reuses the pty driver from play.py."""
import os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
spec = importlib.util.spec_from_file_location("driver", os.path.join(os.path.dirname(os.path.abspath(__file__)), "play.py"))

# --- inline the driver bits instead (play.py runs a scenario on import) ---
import pty, select, subprocess

ROOT = "/Users/ivan/Desktop/workbin/code/sheetcircuit"
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "play3_transcript.log")
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
out = g.read_until(r"Choice: ")
m0, lv, xp = status(out)
note(f"boot: ${m0} Lv{lv}")

# buy the strongest affordable E car
out = g.do("m", r"Choice: ")
out = g.do("buy", r"Buy.*: ")
g.send("eurovan_cup"); out = settle()
money, _, _ = status(out)
note(f"bought eurovan_cup, ${money}")
g.send("b"); out = g.read_until(r"Choice: ")

# tune it: stage a REAL change (1.8 differs from default 2.0) and apply
out = g.do("t", r"Car: ")
out = g.do("eurovan_cup", r"Section: ")
out = g.do("1", r"Field: ")
out = g.do("1", r"Value \(")
out = g.do("1.8", r"Field: ")
if not re.search(r"1\.8", out):
    flag(f"tune: staged 1.8 not shown; tail {out[-250:]!r}")
out = g.do("b", r"Section: ")                 # apply lives at the sections menu
g.send("w"); out = settle(r"Section: |Choice: ", 20)
if not re.search(r"[Aa]pplied|Setup applied|applied", out):
    flag(f"tune apply (w at sections menu): no confirmation; tail {out[-300:]!r}")
else:
    note("tune apply confirmed at sections menu")
for _ in range(4):
    if out.rstrip().endswith("Choice:"):
        break
    g.send("b"); out = g.read_until(r"(?:Choice|Section|Field|Car): |apply & exit", 15)
    if "apply & exit" in out:
        g.send("d"); out = g.read_until(r"(?:Choice|Car): ", 15)

RACE_CAR = "eurovan_cup"
def run_race(event_id):
    out = g.do("r", r"Event: ")
    out = g.do(event_id, r"Car: ")
    out = g.do(RACE_CAR, r"Driver: ")
    out = g.do("driver_novak", r"Lap |command", 60)
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
    return out


level, races = 1, 0
bought_d_car = False
for i in range(30):
    if level >= 2 and not bought_d_car:
        out = g.do("m", r"Choice: ")
        out = g.do("buy", r"Buy.*: ")
        g.send("nagoya_march_super"); out = settle()
        money, _, _ = status(out)
        note(f"Lv2 reached: bought nagoya_march_super for D events, ${money}")
        g.send("b"); g.read_until(r"Choice: ")
        out = repair("nagoya_march_super")
        money, _, _ = status(out)
        note(f"repaired nagoya to full, ${money}")
        RACE_CAR = "nagoya_march_super"
        bought_d_car = True
    ev = "sunday_cup" if level < 2 else ("clubman_trial" if i % 2 == 0 else "oval_night")
    try:
        out = run_race(ev)
    except (TimeoutError, RuntimeError) as exc:
        flag(f"race {i+1} ({ev}) failed: {exc}")
        break
    races += 1
    money, level, xp = status(out)
    prize = re.search(r"Prize: \$(\d+)", out)
    teamxp = re.search(r"Team XP\s+\+(\d+)", out)
    cond = re.findall(r"Overall\s+(\d+)%", out)
    condition = int(cond[-1]) if cond else -1
    note(f"race {races}: {ev} prize=${prize.group(1) if prize else '?'} +{teamxp.group(1) if teamxp else '?'}xp -> ${money} Lv{level} {xp}xp cond={condition}%")
    if money < 700:
        flag(f"nearly broke at ${money} after race {races}")
        break
    if level >= 3:
        note(f"TEAM LEVEL 3 after {races} races, ${money}")
        break
    if 0 <= condition < 70:
        out = repair(RACE_CAR)
        money, _, _ = status(out)
        note(f"repaired {RACE_CAR}, ${money}")
else:
    flag(f"did not reach Lv3 in {races} races")

# save + quit (save prompts for a path; accept default)
out = g.do("s", r"Path: ")
g.send(""); out = settle()
if "aved" not in out:
    flag(f"save: no confirmation; tail {out[-200:]!r}")
else:
    note("saved to default path")
g.send("q")
g.read_until(r"y/N|[Qq]uit", 10)
g.send("y")
time.sleep(1.0)
if g.proc.poll() is None:
    g.proc.terminate()
    flag("quit did not exit process")

print("\n=== CHECKPOINTS ===")
for c in checkpoints: print(" -", c)
print("\n=== ANOMALIES ===" if anomalies else "\n=== NO ANOMALIES ===")
for a in anomalies: print(" -", a)
