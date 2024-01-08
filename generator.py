from enum import Enum
from zipfile import ZipFile
from random import shuffle
import os
import shutil
import re
from pathlib import Path
from pydub import AudioSegment
from pydub.generators import Sine

# Metronome audio creation
metronomeDir = Path(__file__).parent / "MetronomeSounds"
outDir = Path(__file__).parent / "out"
def createMetronomeSegment(bpm, measures, output_file, meter=4, metronomestyle="default", gain=20):
    # Get metronme sound samples
    hiSound = None
    loSound = None
    for filePath in (metronomeDir / metronomestyle).iterdir():
        if filePath.is_dir(): continue
        if filePath.stem.endswith("hi") and hiSound is None:
            hiSound = AudioSegment.from_file(filePath)
        elif filePath.stem.endswith("lo") and loSound is None:
            loSound = AudioSegment.from_file(filePath)
    if hiSound is None or loSound is None:
        raise Exception("invalid metronome style")

    # Create audio segment
    millisecondsPerBeat = 60000 / bpm
    totalDuration = millisecondsPerBeat * meter * measures + millisecondsPerBeat
    metronomeSegment = AudioSegment.silent(totalDuration + max(len(hiSound), len(loSound)))
    currentTime = 0
    for measure in range(measures):
        metronomeSegment = metronomeSegment.overlay(hiSound, position=currentTime)
        currentTime += millisecondsPerBeat
        for beat in range(1, meter):
            metronomeSegment = metronomeSegment.overlay(loSound, position=currentTime)
            currentTime += millisecondsPerBeat
    metronomeSegment = metronomeSegment.overlay(hiSound, position=currentTime)
    currentTime += millisecondsPerBeat
    metronomeSegment += gain
    return metronomeSegment

# 4K pattern creation
numLanes = 4
beatSubdivision = 4 # 16th notes (4 per beat)

class Pattern(Enum):
    SingleStream = 1
    LightJumpstream = 2
    DenseJumpstream = 3
    LightHandstream = 4
    DenseHandstream = 5
    Jumpjack = 6
    LightChordjack = 7
    DenseChordjack = 8
    Quadjack = 9

def noteLength(note):
    return note.count(True)

def randomNote(length=1):
    # random note of given length
    if length > numLanes: raise Exception("invalid pattern")
    note = [True]*length + [False]*(numLanes - length)
    shuffle(note)
    return note

def randomStreamNote(prevNote, length=1):
    # new note of given length that doesn't create a jack with prev note
    availableNotes = numLanes - noteLength(prevNote)
    if availableNotes <= 0 or length > availableNotes: raise Exception("invalid pattern")
    noteOverlay = [True]*length + [False]*(availableNotes - length)
    shuffle(noteOverlay)
    note = [False]*numLanes
    i = 0
    for j in range(numLanes):
        if prevNote[j]: continue
        note[j] = noteOverlay[i]
        i += 1
    return note

def generatePatternNote(pattern, subdivision, prevNote):
    # generate note based on subdivision within measure and prevNote
    if pattern == Pattern.SingleStream:
        return randomStreamNote(prevNote)
    elif pattern == Pattern.LightJumpstream:
        return randomStreamNote(prevNote, 2 if subdivision == 0 else 1)
    elif pattern == Pattern.DenseJumpstream:
        return randomStreamNote(prevNote, 2 if subdivision % 2 == 0 else 1)
    elif pattern == Pattern.LightHandstream:
        return randomStreamNote(prevNote, 3 if subdivision == 0 else 1)
    elif pattern == Pattern.DenseHandstream:
        if subdivision == 0: return randomStreamNote(prevNote, min(3, numLanes - noteLength(prevNote)))
        elif subdivision % 4 == 0: return randomStreamNote(prevNote, 3)
        elif subdivision % 2 == 0: return randomStreamNote(prevNote, 2)
        else: return randomStreamNote(prevNote)
    elif pattern == Pattern.Jumpjack:
        return randomNote(2)
    elif pattern == Pattern.LightChordjack:
        return randomNote(3 if subdivision % 2 == 0 else 2)
    elif pattern == Pattern.DenseChordjack:
        return randomNote(4 if subdivision == 0 else 3)
    elif pattern == Pattern.Quadjack:
        return randomNote(4)
    else:
        raise Exception("invalid pattern")

def createPatternSequence(pattern, measures, meter=4):
    # Notes are lists or tuples of booleans, one for each lane
    currentNote = 0
    notes = []
    for _ in range(measures):
        for _ in range(meter):
            for subdivision in range(beatSubdivision): # sixteenth notes
                prevNote = [False]*numLanes if currentNote == 0 else notes[currentNote - 1]
                notes.append(generatePatternNote(pattern, subdivision, prevNote))
                currentNote += 1

    notes.append(generatePatternNote(pattern, 0, notes[currentNote - 1]))
    currentNote += 1

    return notes

# qua file creation
def createQuaFile(path, patternSequence, bpm, title="Pattern Generator", diffname="1", audioName="audio.mp3"):
    with open(path, "w+") as quaFile:
        quaFile.write(f"AudioFile: {audioName}\n")
        quaFile.write("BackgroundFile: ''\n")
        quaFile.write("MapId: -1\n")
        quaFile.write("MapSetId: -1\n")
        quaFile.write("Mode: Keys4\n")
        quaFile.write(f"Title: {title}\n")
        quaFile.write("Artist: ''\n")
        quaFile.write("Source: ''\n")
        quaFile.write("Tags: ''\n")
        quaFile.write("Creator: RayCurse\n")
        quaFile.write(f"DifficultyName: {diffname}\n")
        quaFile.write("Description: This is an auto generated map.\n")
        quaFile.write("BPMDoesNotAffectScrollVelocity: true\n")
        quaFile.write("InitialScrollVelocity: 1\n")
        quaFile.write("EditorLayers: []\n")
        quaFile.write("CustomAudioSamples: []\n")
        quaFile.write("SoundEffects: []\n")
        quaFile.write("TimingPoints:\n")
        quaFile.write("- StartTime: 0\n")
        quaFile.write(f"  Bpm: {bpm}\n")
        quaFile.write("SliderVelocities: []\n")
        quaFile.write("HitObjects:\n")

        currentTime = 0
        currentBeatSubdivisionTime = 0
        millisecondsPerBeat = 60000 / bpm
        millisecondsPerSubdivision = millisecondsPerBeat / beatSubdivision
        for i, note in enumerate(patternSequence):
            for j, x in enumerate(note):
                if not x: continue
                quaFile.write(f"- StartTime: {int(currentTime + currentBeatSubdivisionTime)}\n")
                quaFile.write(f"  Lane: {j + 1}\n")
                quaFile.write("  KeySounds: []\n")
            currentBeatSubdivisionTime += millisecondsPerSubdivision
            if i % beatSubdivision == beatSubdivision - 1:
                currentTime += millisecondsPerBeat
                currentBeatSubdivisionTime = 0

if __name__ == "__main__":
    shutil.rmtree(outDir)
    os.mkdir(outDir)

    bpm = 180
    measures = 32
    meter = 4

    print("Creating audio...")
    audioSegment = createMetronomeSegment(bpm, measures, "out.mp3")
    print("Creating patterns...")
    seq = createPatternSequence(Pattern.DenseHandstream, measures)
    print("Exporting...")

    os.mkdir(outDir / "output")
    audioSegment.export(outDir / "output" / "audio.mp3", format="mp3")
    createQuaFile(outDir / "output" / "a.qua", seq, bpm)
    shutil.make_archive(str(outDir / "output"), "zip", outDir / "output")
    shutil.copyfile(outDir / "output.zip", Path(__file__).parent / "output.qp")
