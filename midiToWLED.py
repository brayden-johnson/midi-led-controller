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
import music21
import PySimpleGUI as sg

from rtmidi.midiutil import open_midiinput
del pywizlight.wizlight.__del__


# Logging
log = logging.getLogger('midiin_poll')
logging.basicConfig(level=logging.DEBUG)

# Functions
def mapRange(value, inMin, inMax, outMin, outMax):
    return outMin + (((value - inMin) / (inMax - inMin)) * (outMax - outMin))

def getLed(config, value):
    #return int(mapRange(value, START_MIDI, END_MIDI, 1, NUM_LEDS))
    ret = config['numLeds'] - (value - config['midiEnd']) * 2
    if( value > config['numLeds'] / 2):
        return ret+1
    if( ret > 0 ):
        return ret
    return 0

def getVelocityAwareRGB(rgbVal, velocity):
    newRGB = [0] * 3
    for i in range(len(rgbVal)):
        newRGB[i] = int((int(mapRange(velocity, 0, 127, 100, 255)) / 255) * rgbVal[i])
    return newRGB

def getGradientRGB(numLeds, rgbVal1, rgbVal2, pos):
    newRGB = [0] * 3
    for i in range(len(newRGB)):
        newRGB[i] = int(mapRange(pos, 1, numLeds, rgbVal1[i], rgbVal2[i]))
    return newRGB

def getRGBValue(config, velocity, pos):
    ## Check if Velocity Aware
    if not config['velocity']:
        velocity = 127 # define as max velocity
    # Modes
    if config['mode'] == "alternating":
        # Alternating color mode
        config['alternating'] = not config['alternating']
        if not (config['alternating']):
            return getVelocityAwareRGB(config['RGB'], velocity)
        else:
            return getVelocityAwareRGB(config['RGB2'], velocity)
    elif config['mode'] == "gradient":
        return getVelocityAwareRGB( getGradientRGB( config['numLeds'], config['RGB'], config['RGB2'], pos ), velocity)
    elif config['mode'] == "solid":
        # Solid color RGB across keyboard
        return getVelocityAwareRGB(config['RGB'], velocity)
    

def sendNoteOn(ser, note, velocity, config):
    if ((note >= config['midiStart']) and (note <= config['midiEnd'])) or ((note >= config['midiEnd']) and (note <= config['midiStart'])):
        led = getLed(config, note)
        data = {"seg":{"i":[led-1, getRGBValue(config, velocity, led), config['numLeds']-led]}}
        data = json.dumps(data)
        ser.write(data.encode('ascii'))
        print(json.loads(data))
        time.sleep(0.01)
    else:
        print("Value out of range: " + str(note))



def sendNoteOff(ser, note, config):
    if ((note >= config['midiStart']) and (note <= config['midiEnd'])) or ((note >= config['midiEnd']) and (note <= config['midiStart'])):
        led = getLed(config, note)
        data = {"seg":{"i":[led-1, [0,0,0], config['numLeds']-led]}}
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
        sceneId = None
        if light[1].get_scene_id() <= 32 and light[1].get_scene_id() >= 1:
            sceneId = light[1].get_scene_id()
        await light[0].turn_on(pywizlight.PilotBuilder(
                #rgb = (light[1].get_rgb() if light[1].get_rgb()[0] else [0,0,0]), 
                brightness=light[1].get_brightness(),
                #warm_white=light[1].get_warm_white(), 
                #cold_white=light[1].get_cold_white(),
                rgbww=light[1].get_rgbww(),
                colortemp=light[1].get_colortemp(),
                ratio=light[1].get_ratio(),
                scene=sceneId
            ))

# Set up Wiz Lights
async def setupLights(data):
    if(data['wizLights']):
        for i in range(len(data['wizLights'])):
            data['lightDevices'][i] = pywizlight.wizlight(data['wizLights'][i])

def lightHandler(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


def setupLightThread(data):
    loop = None
    if not data['lightLoop']:
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=lightHandler, args=(loop,), daemon=True)
        thread.start()
    else:
        loop = data['lightLoop']

    asyncio.run_coroutine_threadsafe(setupLights(data), loop)
    # Get Current State
    future = asyncio.run_coroutine_threadsafe(saveStates(data['lights']), loop)
    future.result()
    return loop

def handleMidiInput(msg, data=None):
    if msg:
        message, deltatime = msg
        data['timer'] += deltatime
        print("[%s] @%0.6f %r" % ("MIDI", data['timer'], message))
        # Check if this is a noteOn Message
        if(message[0] == 144):
            # # Add to cached notes
            if len(data['cachedNotes']) >= 20:
                data['cachedNotes'].pop(0)
            data['cachedNotes'].append(music21.note.Note(music21.pitch.Pitch(message[1])))
            # Note on/off.. check for sustain/held 
            if not data['sustain']:
                # Not Sustaining. Check if note is held.
                if message[1] in data['heldNotes']:
                    # Is currently held. Send an off message and remove from heldNotes
                    data['heldNotes'].pop(message[1])
                    sendNoteOff(data['serial'], message[1], data['config'])
                else:
                    # Not being held. Add and send
                    data['heldNotes'][message[1]] = 127
                    sendNoteOn(data['serial'], message[1], message[2], data['config'])
            else:
                # Sustaining. If holding, then we are releasing and should remove from heldNotes but keep in sustainedNotes. Don't send serial.
                if message[1] in data['heldNotes']:
                    data['heldNotes'].pop(message[1])
                    pass
                elif message[1] in data['sustainedNotes']:
                    # Not holding, but already been sustained, just add to held notes
                    data['heldNotes'][message[1]] = message[2]
                    # However, update velocity // NEW
                    data['sustainedNotes'][message[1]] = message[2]
                    sendNoteOn(data['serial'], message[1], message[2], data['config'])
                else:    
                    # Not holding. Add to held notes and sustained. Send serial.
                    data['heldNotes'][message[1]] = message[2]
                    data['sustainedNotes'][message[1]] = message[2]
                    sendNoteOn(data['serial'], message[1], message[2], data['config'])
        elif(data['config']['sustain'] and message[0] == 176 and message[1] == 64):
            # Damper Pedal Control.. invert sustain and handle
            if(data['sustain']):
                data['sustain'] = False
                # Remote all sustained notes. Send a serial message to turn off the LEDs not still held
                for index, velocity in data['sustainedNotes'].items():
                    if not index in data['heldNotes']:
                        # The note isn't being held. Send a message to turn off light
                        sendNoteOff(data['serial'], index, data['config'])
                data['sustainedNotes'] = {}
            else:
                data['sustain'] = True
                # Sustain is on. Subsequent notes should be sustained and currently held notes should be held in sustain
                data['sustainedNotes'] = data['heldNotes'].copy()
                # Check if there are notes being held and sustained or not
        
        # Lights
        if(data['config']['lights']):
            if(len(data['sustainedNotes']) == 0 and len(data['heldNotes']) == 0):
                for light in data['lights']:
                    future = asyncio.run_coroutine_threadsafe(updateLight(light[0], [0,0,0], 0), data['lightLoop'])
            else:
                for i in range(len(data['lights'])):
                    light = data['lights'][i]
                    if(data['config']['mode'] != "solid" and i % 2 == 1):
                        future = asyncio.run_coroutine_threadsafe(updateLight(light[0], data['config']['RGB'], 255), data['lightLoop'])
                    else:
                        future = asyncio.run_coroutine_threadsafe(updateLight(light[0], data['config']['RGB2'], 255), data['lightLoop'])
                        
                    


# except KeyboardInterrupt:
#     print('')
# finally:
#     print("Exit.")
#     midiin.close_port()
#     endLoop = asyncio.get_event_loop()
#     endLoop.run_until_complete(updateLightStates(LIGHTS))
#     del midiin