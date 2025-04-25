#!/usr/bin/env python3
import math
import numpy
import os
import pyaudio
import queue
import threading

from optparse import OptionParser

class Morse():
    morse_elements = {
        'a': 0x06,
        'b': 0x11,
        'c': 0x15,
        'd': 0x09,
        'e': 0x02,
        'f': 0x14,
        'g': 0x0b,
        'h': 0x10,
        'i': 0x04,
        'j': 0x1e,
        'k': 0x0d,
        'l': 0x12,
        'm': 0x07,
        'n': 0x05,
        'o': 0x0f,
        'p': 0x16,
        'q': 0x1b,
        'r': 0x0a,
        's': 0x08,
        't': 0x03,
        'u': 0x0c,
        'v': 0x18,
        'w': 0x0e,
        'x': 0x19,
        'y': 0x1d,
        'z': 0x13,
        '0': 0x3f,
        '1': 0x3e,
        '2': 0x3c,
        '3': 0x38,
        '4': 0x30,
        '5': 0x20,
        '6': 0x21,
        '7': 0x23,
        '8': 0x27,
        '9': 0x2f,
        ',': 0x73,
        '-': 0x61,
        '.': 0x6a,
        '/': 0x29,
        '?': 0x4c,
        ':': 0x47,
        ';': 0x55,
        '(': 0x2d, # KN
        '+': 0x2a, # AR
        '=': 0x31, # BT
        '%': 0x22, # AS
        '*': 0x68, # SK
        '!': 0x28, # VE
        '\\': 0x80 # ERROR
    }

    def __init__(self, wpm=20, pitch=600, sample_rate=48000):
        self.wpm = wpm
        self.pitch = pitch
        self.rate = sample_rate

        self.generate_elements()

    def samples_per_element(self):
        return self.samples_per_dit

    def on_cycle(self):
        sample_count = int(self.rate / self.pitch)
        samples = []
        for i in range(self.samples_per_cycle):
            sample = math.sin(2 * math.pi * i/self.samples_per_cycle)
            samples.append(sample)
        samples = numpy.array(samples, dtype=numpy.float32) / 10
        samples = samples.repeat(2)     # stereo
        return samples

    def off_cycle(self):
        samples = numpy.zeros(self.samples_per_cycle, dtype=numpy.float32)
        samples = samples.repeat(2)     # stereo
        return samples

    def generate_elements(self):
        self.samples_per_cycle = int(self.rate / self.pitch)
        self.samples_per_dit = int(self.rate * 1.2 / self.wpm)

        cycles_per_dit = int(self.samples_per_dit / self.samples_per_cycle)
        cycles_per_element_space = cycles_per_dit
        cycles_per_dah = cycles_per_dit * 3
        cycles_per_character_space = cycles_per_dah
        cycles_per_word_space = cycles_per_dah * 2

        on_cycle = self.on_cycle()
        off_cycle = self.off_cycle()
        dit = numpy.tile(on_cycle, cycles_per_dit)
        dah = numpy.tile(on_cycle, cycles_per_dah)
        element_space = numpy.tile(off_cycle, cycles_per_element_space)
        character_space = numpy.tile(off_cycle, cycles_per_character_space)
        word_space = numpy.tile(off_cycle, cycles_per_word_space)
        self.dit = dit.tobytes()
        self.dah = dah.tobytes()
        self.element_space = element_space.tobytes()
        self.character_space = character_space.tobytes()
        self.word_space = word_space.tobytes()

    def set_wpm(self, wpm):
        self.wpm = wpm
        self.generate_elements()

    def set_pitch(self, pitch):
        self.pitch = pitch
        self.generate_elements()

    def set_sample_rate(self, sample_rate):
        self.rate = sample_rate
        self.generate_elements()


    def character_elements(self, c):
        if c == ' ':
            return (self.word_space,)

        if c not in self.morse_elements:
            return None

        elements = []
        v = self.morse_elements[c]
        while v > 1:
            if v & 1:
                elements.append(self.dah)
            else:
                elements.append(self.dit)
            elements.append(self.element_space)
            v >>= 1
        elements.append(self.character_space)
        return elements

class Output():
    def __init__(self, device_index, sample_rate, frames_per_buffer):
        self.pa = self.pyaudio()
        self.stream = self.pa.open(
            format=pyaudio.paFloat32,
            channels=2,  # stereo
            rate=sample_rate,
            frames_per_buffer=frames_per_buffer,
            output=True,
            output_device_index=device_index
        )

        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self.write, name='output_thread')
        self.thread.start()

    def pyaudio(self):
        fd = os.dup(2)
        os.close(2)              # Close stderr because pyaudio outputs a lot of disquieting messages
        pa = pyaudio.PyAudio()
        os.dup2(fd, 2)           # restore stderr
        os.close(fd)
        return pa

    def put(self, elements):
        self.queue.put(elements)

    def write(self):
        while True:
            outputs = self.queue.get()
            if len(outputs) == 0:
                break
            for output in outputs:
                self.stream.write(output)

    def close(self):
        self.put([])
        self.thread.join()
        self.stream.stop_stream()
        self.stream.close()
        self.pa.terminate()

class Options():
    @staticmethod
    def parse():
        parser = OptionParser()
        parser.add_option('-w', '--wpm', dest='wpm', default=20,
                          help="words per minute")
        parser.add_option('-p', '--pitch', dest='pitch', default = 600,
                          help="audio pitch")
        parser.add_option('-r', '--rate', '--sample_rate', dest='sample_rate', default=48000,
                          help="audio device sample rate")
        parser.add_option('-d', '--device', '--device_index', dest='device_index', default=1,
                          help="output audio device index")
        (options, args) = parser.parse_args()

        Options.wpm = int(options.wpm)
        Options.pitch = int(options.pitch)
        Options.sample_rate = int(options.sample_rate)
        Options.device_index = int(options.device_index)

        if len(args) != 0:
            parser.error("Unexpected argument '{arg}'".format(arg=args[0]))

def main():
    Options.parse()
    wpm = Options.wpm
    pitch = Options.pitch
    sample_rate = Options.sample_rate
    device_index = Options.device_index

    morse = Morse(wpm=wpm, pitch=pitch, sample_rate=sample_rate)
    output = Output(device_index, sample_rate, morse.samples_per_element())

    while True:
        try:
            line = input()
        except:
            break

        for c in line:
            elements = morse.character_elements(c)
            if elements == None:
                continue
            output.put(elements)

    output.close()

if __name__ == '__main__':
    main()

# vim: set expandtab ts=4 sw=4:
