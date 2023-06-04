from __future__ import print_function



import serial
import serial.tools.list_ports
import threading
import time
import json
import asyncio
import pathlib
# import pychord
# import mingus.core.chords as ChordFinder
# import pretty_midi
from itertools import permutations
from nicegui import ui


from rtmidi.midiutil import open_midiinput
import rtmidi
import midiToWLED

# Color Conversion Methods
def rgb_to_hex(rgb):
    rgb = tuple(rgb)
    return '#%02x%02x%02x' % rgb

def hex_to_rgb(value):
    value = value.lstrip('#')
    lv = len(value)
    return tuple(int(value[i:i+lv//3], 16) for i in range(0, lv, lv//3))

# Set default values for config options in case config file 
# Get predefined configuration options:
class Config:
    def __init__(self):
        self.baud = 921600
        self.midiStart = 100
        self.midiEnd = 28
        self.numLeds = 144
        self.comPort = None
        self.RGB = [255,0,0]
        self.RGB2 = [255,0,0]
        self.mode = "solid"
        self.midiDevice = None
        self.sustain = True
        self.velocity = False
        self.alternating = False

config = Config()

try:
    with open(pathlib.Path("~/Documents/LEDController/config.json").expanduser().resolve(), "r") as jsonfile:
        configVals = json.load(jsonfile)
        for index, val in configVals:
            config.index = val
        print("Read successful.\n")
except:
    print("Read fail. Config file does not exist. File will be written upon exit")

# Create timer
timer = time.time()

# Get Midi Ports
midiPorts = rtmidi.MidiIn().get_ports()
trimmedPorts = [port[:-1].strip() for port in midiPorts]

# Get serial ports
comPorts = serial.tools.list_ports.comports()
ports = [port.name for port in comPorts]

# Define Serial Connection
ser = serial.Serial()
ser.baudrate = config.baud
ser.port = config.comPort
ser.timeout = 10
ser.bytesize=8

# Define Midi Connection
midiin = None

# # Define midi config function
# def getNewMidiValue():
#     if midiPortConfig is None:
#         sg.Popup("Please select a midi device before proceding")
#         return
#     else:
#         global midiin
#         if not running:
#             # Not running, open midi port
#             midiin, portname = rtmidi.midiutil.open_midiinput(midiPortConfig)
#         # Get the value
#         message, deltatime = midiin.get_message()
#         if(message[0] == 144):
#             return message[1]

# Define baud rate options
baudOptions = [115200, 230400, 460800, 500000, 576000, 921600, 1000000, 1500000]

# Define modes options
modes = ['solid', 'alternating', 'gradient', 'rainbowGradient']

# Define data
data = {
    'config': config,
    'sustain': False,
    'sustainedNotes': {},
    'heldNotes': {},
    'timer': timer,
    'serial': ser,
}

# Define running
class Running:
    def __init__(self):
        self.running = False
        self.buttonText = 'RUN'
        self.runnable = False

running = Running()

def runScript():
    global running
    if running.running:
        # Stop
        running.running = False
        running.buttonText='RUN'
        exitData = {"state":{"on": False}}
        exitData = json.dumps(exitData)
        ser.write(exitData.encode('ascii'))
        ser.close()
        midiin.close_port()
        print("CLOSED!")
    else:
        if(running.runnable):
            running.running = True
            ser.open()
            # Save state and set brightness
            initData = {"state":{"on": True, "bri": 255}}
            initData = json.dumps(initData)
            ser.write(initData.encode('ascii'))
            midiin, portname = rtmidi.midiutil.open_midiinput(config.midiDevice)
            midiin.set_callback(midiToWLED.handleMidiInput, data=data)
            running.buttonText='STOP'
            print("RUNNING!")
        else:
            print("Error.")

def checkRunnable():
    running.runnable = config.baud is not None and config.midiDevice is not None and config.comPort is not None

def getMidiPort(val):
    if val is None:
        return None
    else:
        return trimmedPorts.index(val)
    
# GUI AND RUN
# First UI Row: Device Config (Serial, Midi, Baud)
with ui.row():
    with ui.column():
        ui.label('MIDI PORT')
        ui.select(trimmedPorts, on_change=checkRunnable).bind_value_to(config, 'midiDevice', forward=getMidiPort).bind_enabled_from(running, 'running', backward=lambda x: not x)
    with ui.column():
        ui.label('LED PORT')
        ui.select(ports, on_change=checkRunnable).bind_value_to(config, 'comPort').bind_value_to(ser, 'port').bind_enabled_from(running, 'running', backward=lambda x: not x)
    with ui.column():
        ui.label('BAUD RATE')
        ui.select(baudOptions, on_change=checkRunnable).bind_value(config, 'baud').bind_value_to(ser, 'baudrate').bind_enabled_from(running, 'running', backward=lambda x: not x)
# Second UI Row: Color & Mode
with ui.row():
    ui.color_input(label='RGB1', value=rgb_to_hex(config.RGB)).bind_value(config, 'RGB', forward=lambda x: hex_to_rgb(x), backward=lambda x: rgb_to_hex(x))
    ui.color_input(label='RGB2', value=rgb_to_hex(config.RGB2)).bind_value(config, 'RGB2', forward=lambda x: hex_to_rgb(x), backward=lambda x: rgb_to_hex(x))
    ui.select(modes).bind_value(config, 'mode')
# Third UI Row: Sustain & Velocity
with ui.row():
    ui.switch("Sustain").bind_value(config, 'sustain')
    ui.switch("Velocity").bind_value(config, 'velocity')
# Button
runButton = ui.button("Run", on_click=runScript).bind_text_from(running, 'buttonText').bind_enabled_from(running, 'runnable')

ui.run()


# CLOSE
try:
    filepath = pathlib.Path("~/Documents/LEDController/").expanduser().resolve()
    if not filepath.exists():
        filepath.mkdir(parents=True, exist_ok=True)
except Exception as e:
    print("Create directory fail :" + str(e))
try:
    with open(filepath.joinpath("./config.json"), "w") as jsonfile:
        json.dump(vars(config), fp=jsonfile)
        print("Write successful.\n")
except Exception as e:
    print("Write fail: " + str(e))