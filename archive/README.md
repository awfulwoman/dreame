# Archive

Manufacturer-supplied material, kept as reference. Nothing here is generated, and voices never change it.

- `sounds.csv` — transcription of the manufacturer's prompts (`ID,Filename,Text`). It defines what each ID means and which IDs a voice must cover.
- `audio/xiaomi/` — the official English voice pack from Xiaomi's servers (`en.tar.gz` in [soundpackage.json](https://awsde0.fds.api.xiaomi.com/dreame-product/dreame.vacuum.p2029/voices/soundpackage.json)). 97 files.
- `audio/firmware/` — the built-in English voice from the robot's read-only firmware (`/audio/EN/`, firmware dated 2022-03-24). 115 files. These are different recordings from `xiaomi/`, not copies. Shared IDs differ in length and content. It adds IDs 116–153 and lacks 80 and 91–100.

The firmware IDs 126–138 and 143–146 are not in `sounds.csv` yet, because they have not been transcribed.
