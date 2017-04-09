#!/usr/bin/python
'''************************************************************************************************
    Pi Temperature Station
    By John M. Wargo
    www.johnwargo.com

    Minor modifications by Rob Lass <r o b _dot_ lass _at_ gmail _dot_ com> to display numbers
    on the sense hat instead of arrows.

    This is a Raspberry Pi project that measures weather values (temperature, humidity and
    pressure) using the Astro Pi Sense HAT then uploads the data to a Weather Underground
    weather station.
************************************************************************************************'''
from __future__ import print_function

import datetime
import os
import sys
import time
from urllib import urlencode

import urllib2
from sense_hat import SenseHat

from config import Config

# ============================================================================
# Constants
# ============================================================================
MEASUREMENT_INTERVAL = 10  # minutes
WEATHER_UPLOAD = True
WU_URL = "http://weatherstation.wunderground.com/weatherstation/updateweatherstation.php"

# modified from https://www.raspberrypi.org/learning/getting-started-with-the-sense-hat/worksheet/
b = [0, 0, 255]  # blue
r = [255, 0, 0]  # red
e = [0, 0, 0]  # empty
x = 'PLACEHOLDER'

zero = [
    x, x, x, x,
    x, e, e, x,
    x, e, e, x,
    x, e, e, x,
    x, e, e, x,
    x, e, e, x,
    x, e, e, x,
    x, x, x, x,
]

one = [
    e, x, x, e,
    e, x, x, e,
    e, x, x, e,
    e, x, x, e,
    e, x, x, e,
    e, x, x, e,
    e, x, x, e,
    e, x, x, e,
]

two = [
    x, x, x, x,
    e, e, e, x,
    e, e, e, x,
    x, x, x, x,
    x, e, e, e,
    x, e, e, e,
    x, e, e, e,
    x, x, x, x,
]

three = [
    x, x, x, x,
    e, e, e, x,
    e, e, e, x,
    x, x, x, x,
    e, e, e, x,
    e, e, e, x,
    e, e, e, x,
    x, x, x, x,
]

four = [
    x, e, e, x,
    x, e, e, x,
    x, e, e, x,
    x, x, x, x,
    e, e, e, x,
    e, e, e, x,
    e, e, e, x,
    e, e, e, x,
]

five = [
    x, x, x, x,
    x, e, e, e,
    x, e, e, e,
    x, x, x, x,
    e, e, e, x,
    e, e, e, x,
    e, e, e, x,
    x, x, x, x,
]

six = [
    x, x, x, x,
    x, e, e, e,
    x, e, e, e,
    x, x, x, x,
    x, e, e, x,
    x, e, e, x,
    x, e, e, x,
    x, x, x, x,
]

seven = [
    x, x, x, x,
    e, e, e, x,
    e, e, e, x,
    e, e, e, x,
    e, e, e, x,
    e, e, e, x,
    e, e, e, x,
    e, e, e, x,
]

eight = [
    x, x, x, x,
    x, e, e, x,
    x, e, e, x,
    x, x, x, x,
    x, e, e, x,
    x, e, e, x,
    x, e, e, x,
    x, x, x, x,
]

nine = [
    x, x, x, x,
    x, e, e, x,
    x, e, e, x,
    x, x, x, x,
    e, e, e, x,
    e, e, e, x,
    e, e, e, x,
    e, e, e, x,
]


def get_display_array(temp):
    numbers = [zero, one, two, three, four, five, six, seven, eight, nine]

    first = numbers[int((temp % 100) / 10)]
    second = numbers[int(temp % 10)]

    # make the first number red, second blue (hard to read if they match)
    first = [b if elem == x else elem for elem in first]
    second = [r if elem == x else elem for elem in second]

    result = []
    for i in range(1, 9):
        for j in range((i-1)*4, i*4):
            result.append(first[j])
        for j in range((i-1)*4, i*4):
            result.append(second[j])
    return result


def c_to_f(input_temp):
    # convert input_temp from Celsius to Fahrenheit
    return (input_temp * 1.8) + 32


def get_cpu_temp():
    # 'borrowed' from https://www.raspberrypi.org/forums/viewtopic.php?f=104&t=111457
    res = os.popen('vcgencmd measure_temp').readline()
    return float(res.replace("temp=", "").replace("'C\n", ""))


# use moving average to smooth readings
def get_smooth(x):
    # do we have the t object?
    if not hasattr(get_smooth, "t"):
        get_smooth.t = [x, x, x]

    # manage the rolling previous values
    get_smooth.t[2] = get_smooth.t[1]
    get_smooth.t[1] = get_smooth.t[0]
    get_smooth.t[0] = x

    # average the three last temperatures
    xs = (get_smooth.t[0] + get_smooth.t[1] + get_smooth.t[2]) / 3
    return xs


def get_temp(sense):
    # ====================================================================
    # Unfortunately, getting an accurate temperature reading from the
    # Sense HAT is improbable, see here:
    # https://www.raspberrypi.org/forums/viewtopic.php?f=104&t=111457
    # so we'll have to do some approximation of the actual temp
    # taking CPU temp into account. The Pi foundation recommended
    # using the following:
    # http://yaab-arduino.blogspot.co.uk/2016/08/accurate-temperature-reading-sensehat.html
    # ====================================================================
    # First, get temp readings from both sensors
    t1 = sense.get_temperature_from_humidity()
    t2 = sense.get_temperature_from_pressure()
    # t becomes the average of the temperatures from both sensors
    t = (t1 + t2) / 2
    # Now, grab the CPU temperature
    t_cpu = get_cpu_temp()
    # Calculate the 'real' temperature compensating for CPU heating
    t_corr = t - ((t_cpu - t) / 1.5)
    # Finally, average out that value across the last three readings
    t_corr = get_smooth(t_corr)
    # Return the calculated temperature
    return t_corr


def main():
    sense = initialize()

    # on startup, just use the previous minute as lastMinute
    last_minute = datetime.datetime.now().minute
    last_minute -= 1
    if last_minute == 0:
        last_minute = 59

    # infinite loop to continuously check weather values
    while 1:
        # The temp measurement smoothing algorithm's accuracy is based
        # on frequent measurements, so we'll take measurements every 5 seconds
        # but only upload on measurement_interval
        current_second = datetime.datetime.now().second
        # are we at the top of the minute or at a 5 second interval?
        if (current_second == 0) or ((current_second % 5) == 0):
            # calculate the temperature
            calc_temp = get_temp(sense)
            # now use it for our purposes
            temp_c = round(calc_temp, 1)
            temp_f = round(c_to_f(calc_temp), 1)
            humidity = round(sense.get_humidity(), 0)
            # convert pressure from millibars to inHg before posting
            pressure = round(sense.get_pressure() * 0.0295300, 1)
            print("Temp: %sF (%sC), Pressure: %s inHg, Humidity: %s%%" %
                  (temp_f, temp_c, pressure, humidity))

            # display temp on LED
            sense.set_pixels(get_display_array(temp_f))

            # get the current minute
            current_minute = datetime.datetime.now().minute
            # is it the same minute as the last time we checked?
            if current_minute != last_minute:
                # reset last_minute to the current_minute
                last_minute = current_minute
                # is minute zero, or divisible by 10?
                # we're only going to take measurements every MEASUREMENT_INTERVAL minutes
                if (current_minute == 0) or ((current_minute % MEASUREMENT_INTERVAL) == 0):
                    # get the reading timestamp
                    now = datetime.datetime.now()
                    print("\n%d minute mark (%d @ %s)"
                          % (MEASUREMENT_INTERVAL, current_minute, str(now)))

                    # Upload the weather data to Weather Underground if enabled
                    if WEATHER_UPLOAD:
                        # From http://wiki.wunderground.com/index.php/PWS_-_Upload_Protocol
                        print("Uploading data to Weather Underground")
                        # build a weather data object
                        weather_data = {
                            "action": "updateraw",
                            "ID": Config.STATION_ID,
                            "PASSWORD": Config.STATION_KEY,
                            "dateutc": "now",
                            "tempf": str(temp_f),
                            "humidity": str(humidity),
                            "baromin": str(pressure),
                        }
                        try:
                            upload_url = WU_URL + "?" + urlencode(weather_data)
                            response = urllib2.urlopen(upload_url)
                            html = response.read()
                            print("Server response:", html)
                            # do something
                            response.close()  # best practice to close the file
                        except:
                            print("Exception:", sys.exc_info()[0], '\n')
                    else:
                        print("Skipping Weather Underground upload")

        # wait a second then check again
        # You can always increase the sleep value below to check less often
        time.sleep(1)  # this should never happen since the above is an infinite loop


def initialize():
    if (MEASUREMENT_INTERVAL is None) or (MEASUREMENT_INTERVAL > 60):
        print("The application's 'MEASUREMENT_INTERVAL' cannot be empty or greater than 60")
        sys.exit(1)

    if Config.STATION_ID is None:
        print("Missing station ID from the Weather Underground configuration file\n")
        sys.exit(1)
    if Config.STATION_KEY is None:
        print("Missing station key from the Weather Underground configuration file\n")
        sys.exit(1)

    try:
        print("Initializing the Sense HAT client")
        sense = SenseHat()
        # write some text to the Sense HAT's 'screen'
        sense.show_message("Init", text_colour=[255, 255, 0], back_colour=[0, 0, 255])
        # clear the screen
        sense.clear()
    except:
        print("Unable to initialize the Sense HAT library:", sys.exc_info()[0])
        sys.exit(1)

    print("Initialization complete!")
    return sense

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting application\n")
        sys.exit(0)
