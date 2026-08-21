"""Take an order in the terminal. No phone number needed.

    python examples/cli.py

Type what a caller would say, in Arabic. Add --silent to skip synthesis.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

import agent as agent_mod  # noqa: E402
import voho  # noqa: E402

OUT = Path("out")
SILENT = "--silent" in sys.argv

# The awkward order: two mains with different options, then a correction.
SCRIPT = [
    "أبغى وجبتين دجاج مشوي، وحدة حارة ووحدة عادية",
    "إيه، بطاطس كبير. لا لا، خلها متوسط",
    "كذا بس",
]


def say(turn: int, text: str) -> None:
    print(f"\n  \033[32mVoho\033[0m  {text}")
    if SILENT:
        return
    try:
        audio = voho.speak(text)
    except voho.VohoError as exc:
        print(f"        (not synthesised: {exc})")
        return
    OUT.mkdir(exist_ok=True)
    path = OUT / f"turn-{turn:02d}.mp3"
    path.write_bytes(audio)
    print(f"        \033[2m{path} · {len(audio) // 1024} KB · voice {voho.DEFAULT_VOICE}\033[0m")


def main() -> None:
    convo = agent_mod.Agent(caller="+966500000000")
    print("\033[2m  Type what the caller says. Enter on its own runs the script. Ctrl-C to stop.\033[0m")

    turn = 0
    say(turn, convo.greeting())

    scripted = iter(SCRIPT)
    while convo.ticket is None:
        try:
            said = input("\n  Caller  ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not said:
            said = next(scripted, "")
            if not said:
                print("  (script finished)")
                return
            print(f"  Caller  {said}")

        turn += 1
        say(turn, convo.reply(said))

    print("\n  \033[2mSent to the point-of-sale system:\033[0m")
    print(json.dumps(convo.ticket, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
