#!/usr/bin/python3

import os
import pyaudio

def pa_is_format_supported(pa, sample_rate, **kwargs):
    fd = os.dup(2)
    os.close(2)              # Close stderr because pyaudio outputs a lot of disquieting messages
    try: 
        supported = pa.is_format_supported(sample_rate, **kwargs)
    except:
        supported = False
    os.dup2(fd, 2)           # restore stderr
    os.close(fd)
    return supported

def main():
    fd = os.dup(2)
    os.close(2)              # Close stderr because pyaudio outputs a lot of disquieting messages
    pa = pyaudio.PyAudio()
    os.dup2(fd, 2)           # restore stderr
    os.close(fd)

    info = pa.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')

    for device_index in range(0, numdevices):
        try:
            info = pa.get_device_info_by_host_api_device_index(0, device_index)
        except:
            continue
        print('name:', info.get('name', None))
        print('    index:', info.get('index', None))
        print('    default sample rate:', info.get('defaultSampleRate', None))
        rates = []
        for input_sample_rate in range(12000, 48000+12000, 12000):
            if pa_is_format_supported(pa, input_sample_rate,
                                      input_device=device_index,
                                      input_channels=1,
                                      output_channels=2,
                                      input_format=pyaudio.paFloat32,
                                      output_format=pyaudio.paFloat32):
                rates.append(str(input_sample_rate))
        if rates:
            rates = ', '.join(rates)
        else:
            rates = 'None'

        print('    supported  input sample rates (multiple of 12000):', rates)

        rates = []
        for output_sample_rate in range(12000, 48000+12000, 12000):
            if pa_is_format_supported(pa, input_sample_rate,
                                      output_device=device_index,
                                      output_channels=2,
                                      output_format=pyaudio.paFloat32):
                rates.append(str(output_sample_rate))
        if rates:
            rates = ', '.join(rates)
        else:
            rates = 'None'

        print('    supported output sample rates (multiple of 12000):', rates)
        print()

if __name__ == '__main__':
    main()

# vim: set expandtab ts=4 sw=4:
