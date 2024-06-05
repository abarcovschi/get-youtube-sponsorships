"""References: 
https://wiki.sponsor.ajay.app/w/API_Docs
https://sponsorblockpy.readthedocs.io/en/latest/
https://stackoverflow.com/questions/67233609/extract-audio-from-youtube-video
https://kkroening.github.io/ffmpeg-python/index.html
https://ffmpeg.org/ffmpeg-filters.html#atrim
"""

import sys
sys.path.append('c:\\Users\\abarc\\Desktop\\andrei\\projects\\Python\\local\\sponsorblock.py')
import ffmpeg
import sponsorblock as sb
from pytube import YouTube
from typing import List, Tuple


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


def get_sponsorship_audio(link: str, sponsorship_timeframe: Tuple[float, float]) -> bytes:
    """Returns a byte literal of the sponsorship audio from the YouTube video, specified by the timeframe using Pytube and ffmpeg.

    Args:
      link (str):
        URL link to a YouTube video.
      sponsorship_timeframe (Tuple[float, float]):
        tuple of the start and stop times of the sponsorship segment.
    
    Returns:
      audio (bytes):
        bytes literal of the audio segment.
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
        # # Write the audio buffer to file for testing
        # with open('audio.wav', 'wb') as f:
        #     f.write(audio)
        return audio


if __name__ == "__main__":
    # initialise sponsorblock client.
    client = sb.Client()

    # youtube video link in text format.
    # yt_link = "https://www.youtube.com/watch?v=2pV8t-n8m8c" # thomas delauer
    yt_link = "https://www.youtube.com/watch?v=Y9N4ylzIbDM" # how history works (duplicate sponsorship segments test).

    sponsorships_timeframes = get_sponsorship_segments(yt_link)

    # extract the audio from the sponsorship segments.
    if sponsorships_timeframes:
        # process each sponsorship segment in this video.
        for sponsorship_timeframe in sponsorships_timeframes:
            audio = get_sponsorship_audio(yt_link, sponsorship_timeframe)
            b=1