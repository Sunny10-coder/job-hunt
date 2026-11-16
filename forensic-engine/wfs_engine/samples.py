"""Synthetic WhatsApp-style datasets.

Used by the 'Load sample case' action and by the automated tests. Everything is
invented: no real conversation content exists in this repository.
"""
from __future__ import annotations

import io
import random
import zipfile
from pathlib import Path
from typing import Any

DEMO_CHAT = """12/28/23, 9:12 PM - Messages and calls are end-to-end encrypted. No one outside of this chat, not even WhatsApp, can read or listen to them.
12/28/23, 9:13 PM - Priya: Hey! Are we still meeting at the station tomorrow?
12/28/23, 9:15 PM - You: Yes, the 8:40 train. I'll get the tickets tonight.
12/28/23, 9:16 PM - Priya: Perfect. Also I booked the hotel near the beach 🏖️
12/28/23, 9:20 PM - You: Nice, thank you 🙏 Did you get the confirmation email?
12/28/23, 9:21 PM - Priya: <Media omitted>
12/28/23, 9:23 PM - Priya: That's the booking PDF. My number is +91 98765 43210 if they call.
12/29/23, 7:02 AM - You: At the station now. Platform 3.
12/29/23, 7:03 AM - Priya: On my way, 5 minutes.
12/29/23, 7:04 AM - You: 👍
12/29/23, 11:45 AM - Priya: This place is amazing, the food is so good 😄
12/29/23, 11:46 AM - You: Told you! Let's do the boat tour after lunch.
12/30/23, 1:10 AM - Priya: Can't sleep, too excited about tomorrow
12/30/23, 1:12 AM - You: Same here. Sunrise at 6?
12/30/23, 1:13 AM - Priya: Yes ☀️
01/03/24, 8:30 PM - Priya: Back home. That was the best trip, thank you ❤️
01/03/24, 8:35 PM - You: Thank you too. Let's plan the next one.
01/04/24, 10:02 AM - Priya: This message was deleted
01/04/24, 10:05 AM - Priya: Sorry, wrong chat 😅
01/09/24, 6:20 PM - Priya: Are you free for a call tonight?
01/09/24, 6:22 PM - You: After 8, yes.
01/09/24, 9:40 PM - Priya: I've been feeling a bit worried about the project deadline
01/09/24, 9:42 PM - You: We can go through it together tomorrow morning.
01/09/24, 9:43 PM - Priya: That would really help <This message was edited>
01/15/24, 2:15 PM - Priya: voice message omitted
01/15/24, 2:18 PM - You: Got it, thanks for the update.
01/21/24, 11:05 AM - You: Sending the draft now.
02/02/24, 7:55 PM - Priya: Looks great! Only one small change on page 4.
02/12/24, 10:30 AM - Priya: Happy birthday! 🎂 Hope you have a wonderful day.
02/12/24, 10:34 AM - You: Thank you so much 🙂
03/01/24, 6:40 PM - Priya: Long time! How have you been?
03/01/24, 7:10 PM - You: Busy but good. You?
03/01/24, 7:12 PM - Priya: Same. Let's catch up soon.
"""

DEMO_GROUP = """01/10/24, 10:00 AM - Rahul created group "Project Falcon"
01/10/24, 10:01 AM - Rahul: Welcome everyone, kickoff at 11 today.
01/10/24, 10:02 AM - Meera: Noted 👍
01/10/24, 10:03 AM - You: I'll prepare the timeline.
01/10/24, 11:30 AM - Meera: <Media omitted>
01/10/24, 11:31 AM - Meera: First draft of the deck.
01/10/24, 11:45 AM - Rahul: Looks good. Deadline is tight, please prioritise the budget.
01/11/24, 9:00 AM - You: Budget review done, sending numbers now.
01/11/24, 9:05 AM - Rahul: Thanks!
01/12/24, 4:20 PM - Meera: Can we move the review to Friday?
01/12/24, 4:25 PM - Rahul: Friday works for me.
01/12/24, 4:26 PM - You: Same here.
01/15/24, 5:00 PM - Rahul changed the subject to "Falcon - final review"
01/15/24, 5:02 PM - Meera: Final version attached below.
01/15/24, 5:03 PM - Meera: image omitted
01/16/24, 8:10 AM - Rahul removed Meera
01/16/24, 8:11 AM - Rahul: Meera has left the project. I'll take over the deck.
"""

MALAYALAM_CHAT = """31/12/2023, 19:05 - അമ്മ: എപ്പോൾ വരും മോനെ?
31/12/2023, 19:07 - You: ഒരു മണിക്കൂർ കൂടി, അമ്മേ.
31/12/2023, 19:08 - അമ്മ: ഭക്ഷണം ചൂടാക്കി വെച്ചിട്ടുണ്ട് 🍲
31/12/2023, 19:10 - You: നന്ദി അമ്മേ ❤️
01/01/2024, 00:02 - അമ്മ: പുതുവത്സരാശംസകൾ!
01/01/2024, 00:05 - You: ആശംസകൾ അമ്മേ 🙂
"""

ARABIC_CHAT = """01/02/24, 2:00 PM - Ahmed: مرحبا، كيف حالك؟
01/02/24, 2:02 PM - You: بخير الحمد لله، وأنت؟
01/02/24, 2:03 PM - Ahmed: بخير شكرا
01/02/24, 2:05 PM - Ahmed: هل تم إرسال الملف؟
01/02/24, 2:06 PM - You: نعم، أرسلته صباحا
"""

SNIPPET_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489000000"
    "0a49444154789c6360000002000100ffff03000006000557bfabd40000000049454e44ae"
    "426082")


def write_sample_files(target: Path) -> dict[str, Any]:
    """Create a small but realistic evidence set (never real conversations)."""
    target.mkdir(parents=True, exist_ok=True)
    chat = target / "WhatsApp Chat with Priya.txt"
    chat.write_text(DEMO_CHAT, encoding="utf-8")
    group = target / "WhatsApp Chat - Project Falcon.txt"
    group.write_text(DEMO_GROUP, encoding="utf-8")
    malayalam = target / "WhatsApp Chat with Amma.txt"
    malayalam.write_text(MALAYALAM_CHAT, encoding="utf-8")
    arabic = target / "WhatsApp Chat with Ahmed.txt"
    arabic.write_text(ARABIC_CHAT, encoding="utf-8")

    zip_path = target / "WhatsApp Chat with Priya.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("WhatsApp Chat with Priya.txt", DEMO_CHAT)
        zf.writestr("IMG-20231229-WA0001.png", SNIPPET_PNG)
        zf.writestr("booking-PDF-20231228.pdf", b"%PDF-1.4\n% synthetic sample\n")
    return {
        "primary": str(zip_path),
        "files": [str(zip_path), str(group), str(malayalam), str(arabic)],
        "note": "Synthetic dataset generated locally - contains no real conversations.",
    }


def merge_for_tests() -> str:
    return DEMO_CHAT + DEMO_GROUP + MALAYALAM_CHAT + ARABIC_CHAT


def big_dataset(messages: int = 20_000, seed: int = 7) -> str:
    """Deterministic large export used for import benchmarks."""
    rnd = random.Random(seed)
    words = ["budget", "meeting", "review", "deadline", "travel", "tickets", "lunch",
             "project", "update", "tomorrow", "weekend", "photos", "family", "station"]
    people = ["Asha", "Rahul", "Meera", "Joseph", "Fatima"]
    lines = []
    minute = 0
    for i in range(messages):
        minute += rnd.choice([1, 2, 3, 7, 15, 40])
        day = 1 + (minute // 1440) % 28
        month = 1 + (minute // (1440 * 28)) % 12
        hour = (minute // 60) % 24
        mins = minute % 60
        sender = "You" if rnd.random() < 0.5 else rnd.choice(people)
        text = " ".join(rnd.sample(words, k=rnd.randint(2, 6)))
        if rnd.random() < 0.04:
            text = "<Media omitted>"
        lines.append(f"{month:02d}/{day:02d}/24, {hour:02d}:{mins:02d} - {sender}: {text}")
    return "\n".join(lines) + "\n"
