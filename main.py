"""References: 
https://wiki.sponsor.ajay.app/w/API_Docs
https://sponsorblockpy.readthedocs.io/en/latest/
https://stackoverflow.com/questions/67233609/extract-audio-from-youtube-video
https://kkroening.github.io/ffmpeg-python/index.html
https://ffmpeg.org/ffmpeg-filters.html#atrim
"""

import os
import sys
sys.path.append('c:\\Users\\abarc\\Desktop\\andrei\\projects\\Python\\local\\sponsorblock.py')
import ffmpeg
import logging
import assemblyai as aai
from google import genai
from googleapiclient.discovery import build
import sponsorblock as sb
from pytubefix import YouTube
from typing import List, Tuple


def setup_logging(arg_folder, filename, console=False, filemode='w+'):
    """Set up logging to a logfile and optionally to the console also, if console param is True."""
    if not os.path.exists(arg_folder): os.makedirs(arg_folder, exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)  # track INFO logging events (default was WARNING)
    root_logger.handlers = []  # clear handlers
    root_logger.addHandler(logging.FileHandler(os.path.join(arg_folder, filename), filemode))  # handler to log to file
    root_logger.handlers[0].setFormatter(logging.Formatter('%(levelname)s:%(asctime)s: %(message)s'))  # log level and message

    if console:
        root_logger.addHandler(logging.StreamHandler(sys.stdout))  # handler to log to console
        root_logger.handlers[1].setFormatter(logging.Formatter('%(levelname)s:%(asctime)s: %(message)s'))


def get_sponsorship_segments(link: str) -> List[Tuple[float, float]]:
    """Returns a list of tuples of start and stop times of sponsorship segments in a YouTube video extracted using Sponsorblock API.

    Args:
      link (str):
        URL link to a YouTube video.
    
    Returns:
      sponsorships_timeframes (List[Tuple[float, float]]):
        list of tuples, where each tuple is the start and stop time for a particular sponsorship segment.
    """

    # get the sponsorship(s) timeframes in seconds.
    segments = client.get_skip_segments(link)
    # each item is a tuple of sponsorship start time and stop time in seconds.
    # keep only sponsorship segments the sponsorblock community flagged as skippable and get the times of those segments.
    sponsorships_timeframes = list(map(lambda sponsor_segment: sponsor_segment.data['segment'], 
            filter(lambda segment: segment.action_type == 'skip', segments)))
    # Sometimes the same segment is listed more than once but with slight time offsets,
    #  filter out these duplicates, keeping only unique segments, 
    #  merging a segment if one segment is part of a longer segment.
    tolerance = 2.0 # upper limit for the gap (sec) between segments' start or stop times.

    def get_unique_sponsorships(timeframes_list, tolerance):
        for i in range(0, len(timeframes_list)-1):
            timeframe1 = timeframes_list[i] # tuple of (start_time, stop_time).
            timeframe2 = timeframes_list[i+1]
            # check if two timeframes correspond to the same sponsorship.
            if abs(timeframe1[0] - timeframe2[0]) < tolerance:
                # timegap between the start times is less than 'tolerance' seconds.
                # segments correspond to the same sponsorship promotion, but one may have an incorrect shorter timeframe.
                # keep the longer stop time and combine the segments into one (start time unchanged as it is the same).
                    timeframes_list[i][1] = max(timeframe1[1], timeframe2[1]) # replace (i)'th tuple's stop time with the largest of the two.
                    del timeframes_list[i+1] # delete (i+1)'st tuple.
                    return True
        return False

    while get_unique_sponsorships(sponsorships_timeframes, tolerance): pass

    return sponsorships_timeframes


def get_sponsorship_audio(link: str, sponsorship_timeframe: Tuple[float, float]) -> str:
    """Returns the temporary filepath of the sponsorship audio from the YouTube video, specified by the timeframe using Pytube and ffmpeg.

    Args:
      link (str):
        URL link to a YouTube video.
      sponsorship_timeframe (Tuple[float, float]):
        tuple of the start and stop times of the sponsorship segment.
    
    Returns:
      temp_filename (string):
        the temporarily saved path to wav file containing the sponsorship segment.
    """

    yt = YouTube(link) # pytube
    stream_url = yt.streams.all()[0].url  # Get the URL of the video stream.

    # Probe the audio streams (use it in case you need information like sample rate):
    #probe = ffmpeg.probe(stream_url)
    #audio_streams = next((stream for stream in probe['streams'] if stream['codec_type'] == 'audio'), None)
    #sample_rate = audio_streams['sample_rate']

    # Read audio into memory buffer.
    # Get the audio using stdout pipe of ffmpeg sub-process.
    # The audio is transcoded to PCM codec in WAC container.
    audio, err = (
        ffmpeg
        .input(stream_url)
        # ffmpeg 'atrim' filter extracting the sponsorship segment of audio and keeping it in memory.
        .audio.filter("atrim", start=sponsorship_timeframe[0], end=sponsorship_timeframe[1])
        .output("pipe:", format='wav', acodec='pcm_s16le')  # Select WAV output format, and pcm_s16le auidio codec. My add ar=sample_rate
        .run(capture_stdout=True))

    if not err:
        temp_filename = 'temp_audio.wav'
        # Write the audio buffer to file temporarily
        with open(temp_filename, 'wb') as f:
            f.write(audio)

        return temp_filename
    

def get_sponsorships_from_video(yt_link: str) -> None:
    sponsorships_timeframes = get_sponsorship_segments(yt_link)

    # extract the audio from the sponsorship segments.
    if sponsorships_timeframes:
        # process each sponsorship segment in this video.
        for sponsorship_timeframe in sponsorships_timeframes:
            audio_filepath = get_sponsorship_audio(yt_link, sponsorship_timeframe)

            # transcribe sponsorship.
            transcript = transcriber.transcribe(audio_filepath)

            if transcript.status == aai.TranscriptStatus.error:
                print(f"Transcription failed: {transcript.error}")
                exit(1)
            
            txt = transcript.text

            # get the sponsorship gist using PaLM.

            # define the user prompt message.
            prompt = "Summarise what product the following advertisement from a YouTube video is about: " + txt
            # create a chatbot and complete the prompt request.
            response = gclient.models.generate_content(model="gemini-2.0-flash", contents=prompt).text
            logging.info(f"The youtube video {yt_link} has the following sponsorship segment: {response}")

            # remove the temporarily created audio file of the sponsorship segment.
            os.remove('temp_audio.wav')


if __name__ == "__main__":
    # initialise sponsorblock client.
    client = sb.Client()

    # sign up at https://aistudio.google.com/app/apikey to get API key.
    # create a PALM_API_KEY environment variable.
    gclient = genai.Client(api_key=os.environ['PALM_API_KEY'])

    # sign up at assemblyai.com to get API key.
    # create a ASSEMBLYAI_API_KEY environment variable.
    aai.settings.api_key = os.environ['ASSEMBLYAI_API_KEY']
    transcriber = aai.Transcriber()

    # set up connectivity to YouTube API, follow tutorial https://www.youtube.com/watch?v=TIZRskDMyA4.
    youtube = build(
        'youtube', 
        'v3',
        developerKey=os.environ['YOUTUBE_API_KEY']
    )

    # set up logging to both log file and console.
    setup_logging(os.getcwd(), 'ads.log', console=True, filemode='w')
    
    channel_handle = '@ThomasDeLauerOfficial'  # the YouTube channel's handle.
    most_recent = 5  # the number of most recent videos to check for ads.

    # Get the ''most_recent' amount of most recent videos for the channel specified by its handle.
    channel_request = youtube.channels().list(
        part="snippet,contentDetails,statistics",
        forHandle=channel_handle
    )
    channel_response = channel_request.execute()
    uploads_playlist_id = channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    # fetch the 'most_recent' amount of most recent videos from the uploads playlist.
    playlist_request = youtube.playlistItems().list(
        part="snippet",
        playlistId=uploads_playlist_id,
        maxResults=most_recent
    )
    playlist_response = playlist_request.execute()

    # create a tuple of (title,URL) for the most recent videos.
    yt_links = []
    for item in playlist_response["items"]:
        video_id = item["snippet"]["resourceId"]["videoId"]
        title = item["snippet"]["title"]
        yt_links.append((title, f"https://www.youtube.com/watch?v={video_id}"))

    # loop through the videos.
    for v in yt_links:
        get_sponsorships_from_video(v[1])

    
            