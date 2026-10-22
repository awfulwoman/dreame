import requests
import csv
from pydub import AudioSegment
import os
import tarfile
import hashlib

VOICEPACK_NAME = "moira"

CSV_SOURCE = "dialog/manufacturer/sounds.csv"
AUDIO_DIR = "audio/generated/"
VOICEPACKS_DIR = "voicepacks/"
VOICEPACK_DIR = os.path.join(VOICEPACKS_DIR, VOICEPACK_NAME)
AUDIO_FILES_DIR = os.path.join(AUDIO_DIR, VOICEPACK_NAME)

if not os.path.exists(AUDIO_DIR):
  os.mkdir(AUDIO_DIR)

if not os.path.exists(VOICEPACK_DIR):
  os.mkdir(VOICEPACK_DIR)



print("Audio output dir: ", AUDIO_FILES_DIR)
print("Voicepack output dir: ", VOICEPACK_DIR)

files = []
if not os.path.exists(AUDIO_FILES_DIR):
  os.mkdir(AUDIO_FILES_DIR)
with open(CSV_SOURCE, 'r') as csvfile:
  reader = csv.reader(csvfile, quotechar='"')
  next(reader, None) # Skip CSV header
  for row in reader:
    print("Processing", row[0], row[2])
    input_file = os.path.join(AUDIO_FILES_DIR, f"{row[0]}.wav")
    output_file = os.path.join(AUDIO_FILES_DIR, f"{row[0]}.ogg")

    # Do whatever you want here to generate your voice files
    os.system("say -v Moira -o {} --data-format=LEF32@32000 {}".format(input_file, row[2]))
    
    audio = AudioSegment.from_wav(input_file)
    audio.export(output_file, format="ogg")
    os.remove(input_file)
    files.append(os.path.abspath(output_file))


voicepack = os.path.join(VOICEPACK_DIR, "voice_pack.tar.gz")

tar = tarfile.open(voicepack, "w:gz")
for file in files:
  tar.add(file)
tar.close()

with open(voicepack, "rb") as f:
    file_hash = hashlib.md5()
    while chunk := f.read(8192):
        file_hash.update(chunk)

print(VOICEPACK_NAME + " md5 hash: " + file_hash.hexdigest())
with open(os.path.join(VOICEPACK_DIR, "voicepack.md5.txt"), 'w') as f:
    f.write(file_hash.hexdigest())   
