import os
import itertools
import shutil
from tempfile import TemporaryDirectory
from enum import Enum
from random import shuffle
from random import sample
from pathlib import Path
from pydub import AudioSegment
fileDir = Path(__file__).parent

# Metronome audio creation
def metronomeDuration(bpm, measures, meter):
    numBeats = meter*measures
    msPerBeat = 60000 / bpm
    duration = 0
    # doing it like this instead of multiplying so that it matches up with what metronomeTiming outputs as the last timing
    for _ in range(numBeats):
        duration += msPerBeat
    return duration

def metronomeTiming(bpm, measures, meter):
    numBeats = meter*measures
    msPerBeat = 60000 / bpm

    # Terminate with (measureNumber = -1, beatNumber = 0, msTiming = ...) so that we know when this ends or where to start for next sequence
    measureNumbers = itertools.chain(itertools.chain.from_iterable(itertools.repeat(i, meter) for i in range(measures)), [-1])
    beatNumbers = itertools.chain(itertools.chain.from_iterable((range(meter) for _ in range(measures))), [0])
    # note that we are adding repeatedly instead of multiplying for msTimings
    msTimings = itertools.islice(itertools.count(0, msPerBeat), 0, numBeats + 1)

    return zip(measureNumbers, beatNumbers, msTimings)

def createMetronomeAudioData(patternSegments, metronomestyle="default", gain=20):
    # Get metronme sound samples
    hiSound = None
    loSound = None
    for filePath in (fileDir / "MetronomeSounds" / metronomestyle).iterdir():
        if filePath.is_dir(): continue
        if filePath.stem.endswith("hi") and hiSound is None:
            hiSound = AudioSegment.from_file(filePath)
        elif filePath.stem.endswith("lo") and loSound is None:
            loSound = AudioSegment.from_file(filePath)
    if hiSound is None or loSound is None:
        raise Exception("invalid metronome style")

    # Create blank audio segment
    totalDuration = 0
    for timing in patternSegments:
        _, bpm, measures, meter, _ = timing
        totalDuration += metronomeDuration(bpm, measures, meter)
    totalDuration += len(hiSound)
    metronomeSegment = AudioSegment.silent(totalDuration)

    # Overlay metronome sounds
    currentTimeOffset = 0
    for i, timing in enumerate(patternSegments):
        _, bpm, measures, meter, _ = timing
        for measureNumber, beatNumber, msTime in metronomeTiming(bpm, measures, meter):
            if measureNumber == -1:
                # only if this is the last timing should we play the single beat that comes after the last measure
                if i == len(patternSegments) - 1:
                    metronomeSegment = metronomeSegment.overlay(hiSound, position=currentTimeOffset + msTime)
                currentTimeOffset += msTime
                break

            sound = hiSound if beatNumber == 0 else loSound
            metronomeSegment = metronomeSegment.overlay(sound, position=currentTimeOffset + msTime)

    metronomeSegment += gain
    return metronomeSegment

# 4K pattern creation
numLanes = 4

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

def randomJackNote(prevNote, length, numOfJacks, excludedJackColumns=None):
    # random note of given length that overlaps with prevNote exactly numOfJacks times on columns that are not in excludedJackColumns

    if length > numLanes: raise Exception("invalid pattern")
    if length < numOfJacks: raise Exception("invalid pattern")

    # numOfJacks takes precedence over excludedJackColumns, that is, if they're not enough available jack columns,
    # random columns will be removed from excludedJackColumns so that there are
    if excludedJackColumns:
        # remove ignored indices that don't overlap with previous note
        extraIndices = list()
        for i in excludedJackColumns:
            if not prevNote[i]: extraIndices.append(i)
        for i in extraIndices:
            excludedJackColumns.remove(i)

        # remove from excludedJackColumns if not enough available jack columns
        if noteLength(prevNote) - len(excludedJackColumns) < numOfJacks:
            excludedJackColumns = set(sample(list(excludedJackColumns), noteLength(prevNote) - numOfJacks))

    # create set of available jack columns
    availableJackColumns = set()
    for i, x in enumerate(prevNote):
        if not x: continue
        if excludedJackColumns is not None and i in excludedJackColumns: continue
        availableJackColumns.add(i)
    numOfJacks = min(numOfJacks, len(availableJackColumns))

    # set jack notes
    newNote = [False] * numLanes
    jackedNotes = set()
    if 0 < numOfJacks:
        jackNoteOverlay = [True]*numOfJacks + [False]*(len(availableJackColumns) - numOfJacks)
        shuffle(jackNoteOverlay)
        i = 0
        for j in range(numLanes):
            if j not in availableJackColumns: continue
            newNote[j] = jackNoteOverlay[i]
            jackedNotes.add(j)
            i += 1

    # set rest of non jack notes
    if length > numOfJacks:
        nonJackNoteOverlay = [True]*(length - numOfJacks) + [False]*(numLanes - noteLength(prevNote) - length + numOfJacks)
        shuffle(nonJackNoteOverlay)
        i = 0
        for j in range(numLanes):
            if prevNote[j]: continue
            newNote[j] = nonJackNoteOverlay[i]
            i += 1

    return newNote, jackedNotes

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

def generatePatternNote(pattern, subdivision, prevNote, prevData=None):
    # generate note based on subdivision within beat and prevNote
    # prevData is the second return value of the previous call to generatePatternNote in this pattern sequence
    # prevData is None for the first note in the pattern sequence
    note = None
    data = None

    if pattern == Pattern.SingleStream:
        note = randomStreamNote(prevNote)

    elif pattern == Pattern.LightJumpstream:
        note = randomStreamNote(prevNote, 2 if subdivision == 0 else 1)

    elif pattern == Pattern.DenseJumpstream:
        note = randomStreamNote(prevNote, 2 if subdivision % 2 == 0 else 1)

    elif pattern == Pattern.LightHandstream:
        note = randomStreamNote(prevNote, 3 if subdivision == 0 else 1)

    elif pattern == Pattern.DenseHandstream:
        if subdivision == 0: note = randomStreamNote(prevNote, min(3, numLanes - noteLength(prevNote)))
        elif subdivision % 4 == 0: note = randomStreamNote(prevNote, 3)
        elif subdivision % 2 == 0: note = randomStreamNote(prevNote, 2)
        else: note = randomStreamNote(prevNote)

    elif pattern == Pattern.Jumpjack:
        note, data = randomJackNote(prevNote, 2, 1, prevData)

    elif pattern == Pattern.LightChordjack:
        length = 3 if subdivision % 2 == 0 else 2
        note, data = randomJackNote(prevNote, length, max(0, length - numLanes + noteLength(prevNote)), prevData)

    elif pattern == Pattern.DenseChordjack:
        length = 4 if subdivision == 0 else 3
        note, data = randomJackNote(prevNote, length, max(0, length - numLanes + noteLength(prevNote)), prevData)

    elif pattern == Pattern.Quadjack:
        note = randomNote(4)

    else:
        raise Exception("invalid pattern")

    return note, data

def createNotePattern(pattern, measures, meter, beatSubdivision, lastnote=False):
    # Notes are lists or tuples of booleans, one for each lane
    currentNoteIndex = 0
    prevData = None
    notes = []
    for _ in range(measures):
        for _ in range(meter):
            for subdivision in range(beatSubdivision):
                prevNote = [False]*numLanes if currentNoteIndex == 0 else notes[currentNoteIndex - 1]
                newNote, data = generatePatternNote(pattern, subdivision, prevNote, prevData)
                notes.append(newNote)
                prevData = data
                currentNoteIndex += 1

    if lastnote:
        finalNote, prevData = generatePatternNote(pattern, 0, notes[currentNoteIndex - 1], prevData)
        notes.append(finalNote)
        currentNoteIndex += 1

    return notes

def printPatternSequence(seq):
    for note in reversed(seq):
        for x in note: print("⬤" if x else " ", end="")
        print("\n", end="")

# qua file creation
def createQuaFile(path, patternData, title="Pattern Generator", diffname="1", audioName="audio.mp3"):
    timingPoints = []
    hitObjects = []
    currentTimeOffset = 0
    for i, patternSegment in enumerate(patternData):
        pattern, bpm, measures, meter, beatSubdivision = patternSegment
        msPerBeat = 60000 / bpm
        msPerSubdivision = msPerBeat / beatSubdivision

        timingPoints.append(
            f"- StartTime: {currentTimeOffset}\n"
            f"  Bpm: {bpm}\n"
            f"  Signature: {meter}\n"
        )

        notes = createNotePattern(pattern, measures, meter, beatSubdivision, lastnote=i==len(patternData)-1)
        currentNoteIndex = 0
        for measureNumber, _, msTime in metronomeTiming(bpm, measures, meter):
            if measureNumber == -1:
                if i == len(patternData) - 1:
                    # If this is the last pattern segment, insert extra note
                    note = notes[currentNoteIndex]
                    for j, x in enumerate(note):
                        if not x: continue
                        hitObjects.append(
                            f"- StartTime: {round(currentTimeOffset + msTime)}\n"
                            f"  Lane: {j + 1}\n"
                            "  KeySounds: []\n"
                        )
                currentTimeOffset += msTime
                break
            beatOffset = 0
            for _ in range(beatSubdivision):
                note = notes[currentNoteIndex]
                for j, x in enumerate(note):
                    if not x: continue
                    hitObjects.append(
                        f"- StartTime: {round(currentTimeOffset + msTime + beatOffset)}\n"
                        f"  Lane: {j + 1}\n"
                        "  KeySounds: []\n"
                    )
                currentNoteIndex += 1
                beatOffset += msPerSubdivision

    with open(path, "w+") as quaFile:
        quaFile.write(
            f"AudioFile: {audioName}\n"
            "BackgroundFile: ''\n"
            "MapId: -1\n"
            "MapSetId: -1\n"
            "Mode: Keys4\n"
            f"Title: {title}\n"
            "Artist: ''\n"
            "Source: ''\n"
            "Tags: ''\n"
            "Creator: RayCurse\n"
            f"DifficultyName: {diffname}\n"
            "Description: This is an auto generated map.\n"
            "BPMDoesNotAffectScrollVelocity: true\n"
            "InitialScrollVelocity: 1\n"
            "EditorLayers: []\n"
            "CustomAudioSamples: []\n"
            "SoundEffects: []\n"
        )
        if len(timingPoints) > 0:
            quaFile.write("TimingPoints:\n")
            quaFile.write("".join(timingPoints))
        quaFile.write("SliderVelocities: []\n")
        if len(hitObjects) > 0:
            quaFile.write("HitObjects:\n")
            quaFile.write("".join(hitObjects))

if __name__ == "__main__":
    patternSegments = [
        # pattern,                  bpm,  measures,  meter,  beatSubdivision
        ( Pattern.LightChordjack,   110,  5,         4,      4               ),
        ( Pattern.DenseHandstream,  200,  8,         4,      4               ),
        ( Pattern.DenseChordjack,   220,  3,         6,      2               ),
    ]

    print("Creating audio...")
    audioData = createMetronomeAudioData(patternSegments, metronomestyle="default")

    print("Exporting...")
    with TemporaryDirectory() as tmpDirName:
        tmpDirPath = Path(tmpDirName)
        audioData.export(tmpDirPath / "audio.mp3", format="mp3")
        createQuaFile(tmpDirPath / "map.qua", patternSegments)
        shutil.make_archive(base_name=str(fileDir / "out"), format="zip", root_dir=tmpDirName)
        shutil.move(fileDir / "out.zip", fileDir / "out.qp")
