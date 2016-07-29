import ConfigParser
import random
from flask import Flask, jsonify, render_template, request
from threading import Thread
import threading
import logging
from logging import handlers
import os
import sys
import re
import time
import pygame
import datetime
from werkzeug.utils import secure_filename, redirect

## apt-get install python-pip python-pygame python-dev
## pip install flask

app = Flask(__name__)
configfilename = "whisper.conf"
configfile = (os.path.join(os.getcwd(), configfilename))
config = ConfigParser.SafeConfigParser()
try:
    with open(configfile,'r') as configfilefp:
        config.readfp(configfilefp)
except:
    print("Could not read " + configfile)
    sys.exit()

debug = config.getboolean("Whisper", "debug")

## Setup logging
logger = logging.getLogger(__name__)
handler = handlers.RotatingFileHandler(config.get("Whisper", "logfile"), maxBytes=500000, backupCount=3)
handler.setLevel(logging.INFO)
if debug:
    logger.setLevel(logging.INFO)
else:
    logger.setLevel(logging.WARN)

formatter = logging.Formatter('%(asctime)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
consoleHandler = logging.StreamHandler()
logger.addHandler(consoleHandler)

## disable access logging if not debug
if not debug:
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

playlist = set()


nexttime = datetime.datetime.now() - datetime.timedelta(days=365)
currenttrack = ""
configsection = "Whisper"

mintime = config.getint("Whisper", "mintime") * 60
maxtime = config.getint("Whisper", "maxtime") * 60
sounddir = config.get("Whisper", "sounddir") + "/"

def get_minutes_diff(onetime, onemoretime):
    diff = onemoretime - onetime
    diff_minutes = (diff.days * 24 * 60) + (diff.seconds/60)
    return diff_minutes

def get_sounds_from_folder(dir):
    return [f for f in os.listdir(dir) if re.search(r'.+\.(wav|ogg|mp3)$', f)]

def play_random_sound():
    global currenttrack, playlist
    if not os.access(sounddir, os.R_OK):
        logger.error("Could not open whispers directory " + sounddir)
    else:
        matches = get_sounds_from_folder(sounddir)
        if(len(matches)) > 0:
            logger.info("Got " + str(len(matches))+ " sound bits in the sound directory")

            if len(playlist) > 0:
                ## filter playlist over existing files
                for soundbit in playlist:
                    if soundbit not in matches:
                        playlist.remove(soundbit)
                    soundfile = random.sample((playlist),1)[0]
            else:
                soundfile = random.sample((matches),1)[0]
            logger.info("Will play " + soundfile)
            if not os.access(sounddir + soundfile, os.R_OK):
                logger.error("Could not read sound file " + soundfile)
            else:
                logger.warning("Now playing " + soundfile)
                pygame.mixer.music.load(sounddir + soundfile)
                currenttrack = soundfile
                pygame.mixer.music.play()
        else:
            logger.error("Could not find any music file in the " + sounddir + " directory.")

def set_next_time():
    global nexttime
    fromtime = random.randint(mintime, maxtime)
    logger.info("Next fromtime will be " + str(fromtime) + " seconds from now" )
    nexttime = datetime.datetime.now()+  datetime.timedelta(0,fromtime)

def soundThread(spEvent):
    logger.error("Sound thread is starting")
    while not spEvent.isSet():
        event_is_set = spEvent.wait()
        if(event_is_set):
            if pygame.mixer.music.get_busy():
                logger.error("Was asked to play a sound, but already playing. Sitting this one out!")
            else:
                logger.info("Mixer is clear, starting playback")
                play_random_sound()
        spEvent.clear()



def dingerThread(spEvent):
    ## Added time sleep so the sound thread is done setting up
    logger.error("Dinger thread is starting")
    while True:
        if datetime.datetime.now() > nexttime:
            logger.info("Time was dinged! Let's rock!")
            set_next_time()
            spEvent.set()
        time.sleep(1)

def persist_config(label, value):
    config.set(configsection, label, str(value))
    config.write(open(configfile,'w'))


@app.route('/current')
def get_current():
    if pygame.mixer.music.get_busy():
        return jsonify(current=currenttrack,
                       playing=True,
                       volume=pygame.mixer.music.get_volume(),
                       nexttime=get_minutes_diff(datetime.datetime.now(),nexttime))
    else:
        return jsonify(playing=False,
                       volume=pygame.mixer.music.get_volume(),
                       nexttime=get_minutes_diff(datetime.datetime.now(), nexttime))

@app.route('/set_volume/<volume>')
def set_volume(volume):
    volumefloat = float(volume)
    pygame.mixer.music.set_volume(volumefloat)
    persist_config("volume",int(volumefloat * 100))
    return jsonify(result="ok")

@app.route('/set_times/<min_time>/<max_time>')
def set_times(min_time, max_time):
    global mintime, maxtime
    mintime = int(float(min_time)) * 60
    maxtime = int(float(max_time)) * 60
    logger.info("Rolling next time due to manual time change")
    set_next_time()
    persist_config("mintime", mintime / 60)
    persist_config("maxtime", maxtime / 60)
    return jsonify(result="ok")

@app.route('/skip')
def skip():
    global nexttime
    logger.info("Forcing a skip by setting a time in the past")
    nexttime = datetime.datetime.now() - datetime.timedelta(days=365)
    return jsonify(result="ok")


@app.route("/playlistadd/<filename>")
def playlistadd(filename):
    global playlist
    playlist.add(filename)
    return jsonify(result="ok")

@app.route("/playlistremove/<filename>")
def playlistremove(filename):
    global playlist
    playlist.remove(filename)
    return jsonify(result="ok")

@app.route('/stop')
def stop():
    if pygame.mixer.music.get_busy():
        pygame.mixer.music.stop()
    return jsonify(result="ok")

@app.route('/savemp3', methods=['POST'])
def save_mp3():
    newfile = request.files['newmp3']
    filename = secure_filename(newfile.filename)
    ## Bijzondere situatie: een geloade soundfile kan niet worden overschreven
    if currenttrack == filename:
        filename = "_" + secure_filename(newfile.filename)
    logger.info("Saving new sound file " + filename)
    newfile.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return redirect("/")

@app.route('/')
def hello_world():
    return render_template('blomwhisper.html', mintime=mintime/60, maxtime=maxtime/60,volume=pygame.mixer.music.get_volume() * 100,sounds=get_sounds_from_folder(sounddir), playlist=playlist)


if __name__ == '__main__':
    logger.error("Starting app at " + str(datetime.datetime.now()))
    logger.info("Now initalizing mixer")
    pygame.mixer.init()
    pygame.mixer.music.set_volume(float(config.getint("Whisper", "volume")) / 100)

    while not pygame.mixer.get_init():
        logger.error("Waiting for mixer to init..")
        time.sleep(1)

    spEvent = threading.Event()
    SoundThread = Thread(target = soundThread, args = (spEvent,))
    SoundThread.daemon = True
    SoundThread.start()

    SPThread = Thread(target = dingerThread, args = (spEvent,))
    SPThread.daemon = True
    SPThread.start()

    app.config['UPLOAD_FOLDER'] = sounddir
    logger.error("Starting app complete")
    app.run(debug=debug,host="0.0.0.0",port=80)



