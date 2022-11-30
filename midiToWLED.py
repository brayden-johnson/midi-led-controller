#!/usr/bin/env python
#
# midiin_poll.py
#
"""Show how to receive MIDI input by polling an input port."""

from __future__ import print_function

import logging
import sys
import time
import json

from rtmidi.midiutil import open_midiinput

# Values
BAUD = 921600
START_MIDI = 100
END_MIDI = 28
NUM_LEDS = 144
PORT = 'COM3'

# COLOR
RGB = [1, 200, 1]


log = logging.getLogger('midiin_poll')
logging.basicConfig(level=logging.DEBUG)

import serial
ser = serial.Serial()
ser.baudrate = BAUD
ser.port = PORT
ser.timeout = 10
ser.bytesize=8
time.sleep(1)
ser.open()

# Prompts user for MIDI input port, unless a valid port number or name
# is given as the first argument on the command line.
# API backend defaults to ALSA on Linux.
port = sys.argv[1] if len(sys.argv) > 1 else None

def mapRange(value, inMin, inMax, outMin, outMax):
    return outMin + (((value - inMin) / (inMax - inMin)) * (outMax - outMin))

def getLed(value):
    return int(mapRange(value, START_MIDI, END_MIDI, 1, NUM_LEDS))

def sendNoteOn(value):
    if ((value >= START_MIDI) and (value <= END_MIDI)) or ((value >= END_MIDI) and (value <= START_MIDI)):
        led = getLed(value)
        data = {"seg":{"i":[led-1, RGB, NUM_LEDS-led]}}
        data = json.dumps(data)
        ser.write(data.encode('ascii'))
        print(json.loads(data))
        time.sleep(0.01)
    else:
        print("Value out of range: " + str(value))

def sendNoteOff(value):
    if ((value >= START_MIDI) and (value <= END_MIDI)) or ((value >= END_MIDI) and (value <= START_MIDI)):
        led = getLed(value)
        data = {"seg":{"i":[led-1, [0,0,0], NUM_LEDS-led]}}
        data = json.dumps(data)
        ser.write(data.encode('ascii'))
        print(json.loads(data))
        time.sleep(0.01)
    else:
        print("Value out of range: " + str(value))

try:
    midiin, port_name = open_midiinput(port)
except (EOFError, KeyboardInterrupt):
    sys.exit()

# print("Setting up with color RGB(" + str(RGB[0]) + ',' + str(RGB[1]) + ',' + str(RGB[2]) + ")...")
# ser.write(chr((255)).encode('latin1'))
# time.sleep(0.01)
# ser.write(chr(RGB[0]).encode('latin1'))
# time.sleep(0.01)
# ser.write(chr(RGB[1]).encode('latin1'))
# time.sleep(0.01)
# ser.write(chr(RGB[2]).encode('latin1'))
# time.sleep(0.01)



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
                        sendNoteOn(message[1])
                else:
                    # Sustaining. If holding, then we are releasing and should remove from heldNotes but keep in sustainedNotes. Don't send serial.
                    if message[1] in heldNotes:
                        heldNotes.pop(message[1])
                        pass
                    elif message[1] in sustainedNotes:
                        # Not holding, but already been sustained, do nothing
                        pass
                    else:    
                        # Not holding. Add to held notes and sustained. Send serial.
                        heldNotes[message[1]] = 127
                        sustainedNotes[message[1]] = 127
                        sendNoteOn(message[1])
            elif(message[0] == 176 and message[1] == 64):
                # Damper Pedal Control.. invert sustain and handle
                if(sustain):
                    # Remote all sustained notes. Send a serial message to turn off the LEDs not still held
                    for index, velocity in sustainedNotes.items():
                        if not index in heldNotes:
                            # The note isn't being held. Send a message to turn off light
                            sendNoteOff(index)
                    sustainedNotes = {}
                    sustain = False
                else:
                    # Sustain is on. Subsequent notes should be sustained and currently held notes should be held in sustain
                    for index, velocity in heldNotes.items():
                        sustainedNotes[index] =  velocity
                    sustain = True

        #time.sleep(0.001)
except KeyboardInterrupt:
    print('')
finally:
    print("Exit.")
    midiin.close_port()
    del midiin