#!/usr/bin/env python
#
# midiin_poll.py
#
"""Show how to receive MIDI input by polling an input port."""

from __future__ import print_function

import logging
import sys
import threading
import time
import json
import pywizlight
import asyncio

from rtmidi.midiutil import open_midiinput
del pywizlight.wizlight.__del__

# Check if file exists
config = []
with open("config.json", "r") as jsonfile:
    config = json.load(jsonfile)
    print("Read successful.\n")


# Values
try:
    BAUD = config['baud']
    START_MIDI = config['midiStart']
    END_MIDI = config['midiEnd']
    REV_LEDS = (END_MIDI - START_MIDI) < 0
    NUM_LEDS = config['numLeds']
    PORT = config['comPort']
    midiPort = config['midiDevice']
    WIZLIGHTS_IPS = config['wizLights']
    LIGHTS = [None] * len(WIZLIGHTS_IPS)
    RGB = config['RGB']
    MAX_LIGHT_NUM_KEYS = 10
except KeyError as e:
    print("ERROR: Missing config item: " + str(e.args[0]))

# Logging
log = logging.getLogger('midiin_poll')
logging.basicConfig(level=logging.DEBUG)

# Serial
import serial
ser = serial.Serial()
ser.baudrate = BAUD
ser.port = PORT
ser.timeout = 10
ser.bytesize=8
time.sleep(1)
ser.open()

# Functions
def mapRange(value, inMin, inMax, outMin, outMax):
    return outMin + (((value - inMin) / (inMax - inMin)) * (outMax - outMin))

def getLed(value):
    #return int(mapRange(value, START_MIDI, END_MIDI, 1, NUM_LEDS))
    ret = NUM_LEDS - (value - END_MIDI) * 2
    if( value > NUM_LEDS / 2):
        return ret+1
    if( ret > 0 ):
        return ret
    return 0

def getVelocityRGB(value):
    newRGB = [0] * 3
    for i in range(len(RGB)):
        newRGB[i] = int((int(mapRange(value, 0, 127, 100, 255)) / 255) * RGB[i])
    return newRGB

def sendNoteOn(note, velocity):
    if ((note >= START_MIDI) and (note <= END_MIDI)) or ((note >= END_MIDI) and (note <= START_MIDI)):
        led = getLed(note)
        data = {"seg":{"i":[led-1, getVelocityRGB(velocity), NUM_LEDS-led]}}
        data = json.dumps(data)
        ser.write(data.encode('ascii'))
        print(json.loads(data))
        time.sleep(0.01)
    else:
        print("Value out of range: " + str(note))

def sendNoteOff(note):
    if ((note >= START_MIDI) and (note <= END_MIDI)) or ((note >= END_MIDI) and (note <= START_MIDI)):
        led = getLed(note)
        data = {"seg":{"i":[led-1, [0,0,0], NUM_LEDS-led]}}
        data = json.dumps(data)
        ser.write(data.encode('ascii'))
        print(json.loads(data))
        time.sleep(0.01)
    else:
        print("Value out of range: " + str(note))

async def updateLight(light, rgbVal, brightness):
    if(rgbVal == [0,0,0]):
        await light.turn_off()
    else:
        await light.turn_on(pywizlight.PilotBuilder(rgbww = (rgbVal[0], rgbVal[1], rgbVal[2], 0, 0), brightness=brightness))
    return

async def saveStates(lights):
    for i in range(len(lights)):
        light = lights[i]
        state = await light.updateState()
        lights[i] = (light, state)

async def updateLightStates(lights):
    for i in range(len(lights)):
        light = lights[i]
        print(repr(light[1]))
        await light[0].turn_on(pywizlight.PilotBuilder(
            #rgb = (light[1].get_rgb() if light[1].get_rgb()[0] else [0,0,0]), 
            brightness=light[1].get_brightness(),
            #warm_white=light[1].get_warm_white(), 
            #cold_white=light[1].get_cold_white(),
            rgbww=light[1].get_rgbww(),
            colortemp=light[1].get_colortemp(),
            ratio=light[1].get_ratio()
        ))

# Open Port
try:
    midiin, port_name = open_midiinput(midiPort)
except (EOFError, KeyboardInterrupt):
    sys.exit()

# Set up Wiz Lights
async def setupLights():
    if(WIZLIGHTS_IPS):
        for i in range(len(WIZLIGHTS_IPS)):
            LIGHTS[i] = pywizlight.wizlight(WIZLIGHTS_IPS[i])

def lightHandler(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


loop = asyncio.new_event_loop()
thread = threading.Thread(target=lightHandler, args=(loop,), daemon=True)
thread.start()

asyncio.run_coroutine_threadsafe(setupLights(), loop)
# Get Current State
asyncio.run_coroutine_threadsafe(saveStates(LIGHTS), loop)
# Main Loop.

print("Entering main loop. Press Control-C to exit.")
try:
    timer = time.time()
    sustain = False
    sustainedNotes = {}
    heldNotes = {}
    while True:
        msg = midiin.get_message()

        if msg:
            message, deltatime = msg
            timer += deltatime
            print("[%s] @%0.6f %r" % (port_name, timer, message))
            # Check if this is a noteOn Message
            if(message[0] == 144):
                # Note on/off.. check for sustain/held 
                if not sustain:
                    # Not Sustaining. Check if note is held.
                    if message[1] in heldNotes:
                        # Is currently held. Send an off message and remove from heldNotes
                        heldNotes.pop(message[1])
                        sendNoteOff(message[1])
                    else:
                        # Not being held. Add and send
                        heldNotes[message[1]] = 127
                        sendNoteOn(message[1], message[2])
                else:
                    # Sustaining. If holding, then we are releasing and should remove from heldNotes but keep in sustainedNotes. Don't send serial.
                    if message[1] in heldNotes:
                        heldNotes.pop(message[1])
                        pass
                    elif message[1] in sustainedNotes:
                        # Not holding, but already been sustained, just add to held notes
                        heldNotes[message[1]] = message[2]
                        # However, update velocity // NEW
                        sustainedNotes[message[1]] = message[2]
                        sendNoteOn(message[1], message[2])
                    else:    
                        # Not holding. Add to held notes and sustained. Send serial.
                        heldNotes[message[1]] = message[2]
                        sustainedNotes[message[1]] = message[2]
                        sendNoteOn(message[1], message[2])
            elif(message[0] == 176 and message[1] == 64):
                # Damper Pedal Control.. invert sustain and handle
                if(sustain):
                    sustain = False
                    # Remote all sustained notes. Send a serial message to turn off the LEDs not still held
                    for index, velocity in sustainedNotes.items():
                        if not index in heldNotes:
                            # The note isn't being held. Send a message to turn off light
                            sendNoteOff(index)
                    sustainedNotes = {}
                else:
                    sustain = True
                    # Sustain is on. Subsequent notes should be sustained and currently held notes should be held in sustain
                    sustainedNotes = heldNotes.copy()
                    # Check if there are notes being held and sustained or not
            
            if(len(sustainedNotes) == 0 and len(heldNotes) == 0):
                for light in LIGHTS:
                    future = asyncio.run_coroutine_threadsafe(updateLight(light[0], [0,0,0], 0), loop)
            else:
                allNotes = sustainedNotes | heldNotes
                brightness = min(int(255 * (len(allNotes) / MAX_LIGHT_NUM_KEYS)), 255)
                print(str(brightness))
                for light in LIGHTS:
                    future = asyncio.run_coroutine_threadsafe(updateLight(light[0], RGB, brightness), loop)
                        
                    


except KeyboardInterrupt:
    print('')
finally:
    print("Exit.")
    midiin.close_port()
    endLoop = asyncio.get_event_loop()
    endLoop.run_until_complete(updateLightStates(LIGHTS))
    del midiin